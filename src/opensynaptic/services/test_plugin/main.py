"""
test_plugin/main.py – ServiceManager-mountable test plugin for OpenSynaptic.

Exposes component tests and stress tests as a service with CLI sub-commands.

Usage via CLI:
    python -u src/main.py plugin-test --suite component
    python -u src/main.py plugin-test --suite stress --workers 8 --total 200
    python -u src/main.py plugin-test --suite all
"""
import io
import json
import sys
import threading
import unittest
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

from opensynaptic.utils import (
    os_log,
    LogMsg,
)
from opensynaptic.services.test_plugin.metrics import (
    aggregate_header_probe,
    aggregate_run_series,
    summary_latency_values,
    series_max,
)


class TestPlugin:
    """ServiceManager-mountable test plugin.

    Runs component and/or stress tests for the OpenSynaptic pipeline.
    Mount it via:
        node.service_manager.mount('test_plugin', TestPlugin(node), config={}, mode='runtime')
        node.service_manager.load('test_plugin')
    """

    def __init__(self, node=None):
        self.node = node
        self._config_path = getattr(node, 'config_path', None) if node else None

    @staticmethod
    def get_required_config():
        return {
            'enabled': True,
            'mode': 'manual',
            'stress_workers': 8,
            'stress_total': 200,
            'stress_sources': 6,
            'stress_runtime': {
                'collector_mode': 'legacy',
                'collector_flush_every': 256,
                'pipeline_mode': 'legacy',
            },
        }

    def auto_load(self):
        os_log.log_with_const('info', LogMsg.PLUGIN_TEST_START, plugin='test_plugin', suite='init')
        return self

    # ------------------------------------------------------------------ #
    #  Suite runners                                                       #
    # ------------------------------------------------------------------ #

    def run_component(self, verbosity=1):
        """Run all unit (component) tests and return (ok_count, fail_count, result)."""
        from opensynaptic.services.test_plugin.component_tests import build_suite
        suite = build_suite()
        runner = unittest.TextTestRunner(verbosity=verbosity, stream=sys.stdout)
        result = runner.run(suite)
        ok = result.testsRun - len(result.failures) - len(result.errors)
        fail = len(result.failures) + len(result.errors)
        return ok, fail, result

    def run_component_parallel(self, verbosity=1, max_class_workers=None, use_processes=False):
        """Run component test *classes* concurrently.

        Parameters
        ----------
        verbosity         : int   – passed to TextTestRunner
        max_class_workers : int   – max concurrent workers (default: number of test classes)
        use_processes     : bool  – when True, each class runs in a separate OS process
                                    via ``ProcessPoolExecutor``; when False (default) uses threads

        Returns (ok_count, fail_count, class_results_list).
        Supports Ctrl+C: prints partial results and exits cleanly.
        """
        from opensynaptic.services.test_plugin.component_tests import build_suite
        from opensynaptic.services.test_plugin.stress_tests import (
            _run_test_class_subprocess,
            _init_worker_ignore_sigint,
        )

        # Build class → tests map from the canonical suite.
        class_map: dict[type, list] = {}
        for test in build_suite():
            class_map.setdefault(type(test), []).append(test)

        num_workers = min(max_class_workers or len(class_map), max(1, len(class_map)))

        # ── raw result rows (cls_name, ok, fail, output) ──────────────────
        raw_rows: list[tuple[str, int, int, str]] = []
        _lock = threading.Lock()
        _interrupted = False

        if use_processes:
            # ── ProcessPoolExecutor path ───────────────────────────────────
            _ppool = ProcessPoolExecutor(
                max_workers=num_workers,
                initializer=_init_worker_ignore_sigint,
            )
            _pfutures: dict = {}
            try:
                for cls in class_map:
                    f = _ppool.submit(_run_test_class_subprocess, cls.__name__, self._config_path)
                    _pfutures[f] = cls.__name__
                for future in as_completed(_pfutures):
                    row_dict = future.result()
                    with _lock:
                        raw_rows.append((
                            row_dict['cls'],
                            row_dict['ok'],
                            row_dict['fail'],
                            row_dict.get('output', ''),
                        ))
            except KeyboardInterrupt:
                _interrupted = True
                print('\n[component] Ctrl+C – cancelling process pool…',
                      file=sys.stderr, flush=True)
                for f in _pfutures:
                    f.cancel()
            finally:
                _ppool.shutdown(wait=False, cancel_futures=True)
        else:
            # ── ThreadPoolExecutor path ────────────────────────────────────
            def _run_cls_thread(cls: type, tests: list) -> tuple[str, int, int, str]:
                stream = io.StringIO()
                suite = unittest.TestSuite(tests)
                runner = unittest.TextTestRunner(verbosity=verbosity, stream=stream)
                result = runner.run(suite)
                ok_n = result.testsRun - len(result.failures) - len(result.errors)
                fail_n = len(result.failures) + len(result.errors)
                return cls.__name__, ok_n, fail_n, stream.getvalue()

            _tpool = ThreadPoolExecutor(max_workers=num_workers)
            _tfutures: dict = {}
            try:
                for cls, tests in class_map.items():
                    f = _tpool.submit(_run_cls_thread, cls, tests)
                    _tfutures[f] = cls.__name__
                for future in as_completed(_tfutures):
                    with _lock:
                        raw_rows.append(future.result())
            except KeyboardInterrupt:
                _interrupted = True
                print('\n[component] Ctrl+C – cancelling thread pool…',
                      file=sys.stderr, flush=True)
                for f in _tfutures:
                    f.cancel()
            finally:
                _tpool.shutdown(wait=False, cancel_futures=True)

        # ── Print results sorted by class name ────────────────────────────
        for cls_name, ok_n, fail_n, output in sorted(raw_rows, key=lambda x: x[0]):
            status = 'OK' if fail_n == 0 else 'FAIL'
            print('[{}] ran={} ok={} fail={} {}'.format(
                cls_name, ok_n + fail_n, ok_n, fail_n, status), flush=True)
            if fail_n > 0 and output.strip():
                print(output.strip(), flush=True)
            elif verbosity >= 2 and output.strip():
                print(output.strip(), flush=True)

        if _interrupted:
            print('[component] partial results – {} classes completed'.format(
                len(raw_rows)), file=sys.stderr, flush=True)

        total_ok = sum(r[1] for r in raw_rows)
        total_fail = sum(r[2] for r in raw_rows)
        return total_ok, total_fail, raw_rows

    def run_stress(self, total=200, workers=8, sources=6, progress=True,
                   core_backend=None, require_rust=False, header_probe_rate=0.0,
                   batch_size=1, processes=1, threads_per_process=None,
                   chain_mode='core'):
        """Run concurrent pipeline stress test and return (summary_dict, fail_count)."""
        from opensynaptic.services.test_plugin.stress_tests import run_stress
        expect_codec_class = 'RsBase62Codec' if require_rust else None
        result, summary = run_stress(
            total=total, workers=workers, sources=sources,
            config_path=self._config_path, progress=progress,
            core_name=core_backend,
            expect_core=core_backend,
            expect_codec_class=expect_codec_class,
            header_probe_rate=header_probe_rate,
            batch_size=batch_size,
            processes=processes,
            threads_per_process=threads_per_process,
            chain_mode=chain_mode,
        )
        return summary, result.fail

    def run_auto_profile(self, total=200, workers=8, sources=6,
                         core_backend=None, require_rust=False, header_probe_rate=0.0,
                         profile_total=100000, profile_runs=1, final_runs=1,
                         process_candidates=None, thread_candidates=None,
                         batch_candidates=None, batch_size=1, progress=True,
                         chain_mode='core'):
        from opensynaptic.services.test_plugin.stress_tests import run_auto_profile
        expect_codec_class = 'RsBase62Codec' if require_rust else None
        return run_auto_profile(
            total=total,
            workers=workers,
            sources=sources,
            config_path=self._config_path,
            core_name=core_backend,
            expect_core=core_backend,
            expect_codec_class=expect_codec_class,
            header_probe_rate=header_probe_rate,
            profile_total=profile_total,
            profile_runs=profile_runs,
            final_runs=final_runs,
            process_candidates=process_candidates,
            thread_candidates=thread_candidates,
            batch_candidates=batch_candidates,
            default_batch_size=batch_size,
            progress=progress,
            chain_mode=chain_mode,
        )

    def run_full_load(self, total=1000000, sources=6, core_backend=None,
                      require_rust=False, header_probe_rate=0.0, progress=True,
                      workers_hint=None, threads_hint=None, batch_hint=None,
                      chain_mode='core'):
        """Stress test that automatically saturates all logical CPUs.

        Calls ``get_full_load_config()`` to determine ``processes``,
        ``threads_per_process``, and ``batch_size``, then delegates to
        ``run_stress()``.

        Returns (summary_dict, fail_count).
        """
        from opensynaptic.services.test_plugin.stress_tests import get_full_load_config
        cfg = get_full_load_config(
            workers_hint=workers_hint,
            threads_hint=threads_hint,
            batch_hint=batch_hint,
        )
        print(
            '[full-load] cpu_count={cpu_count} processes={processes} '
            'threads_per_process={threads_per_process} batch_size={batch_size}'.format(**cfg),
            flush=True,
        )
        return self.run_stress(
            total=total,
            workers=cfg['workers'],
            sources=sources,
            progress=progress,
            core_backend=core_backend,
            require_rust=require_rust,
            header_probe_rate=header_probe_rate,
            batch_size=cfg['batch_size'],
            processes=cfg['processes'],
            threads_per_process=cfg['threads_per_process'],
            chain_mode=chain_mode,
        )

    def run_all(self, stress_total=200, stress_workers=8, stress_sources=6, verbosity=1,
                progress=True, core_backend=None, require_rust=False, header_probe_rate=0.0,
                batch_size=1, processes=1, threads_per_process=None,
                chain_mode='core'):
        """Run both component and stress suites. Returns combined report dict."""
        print('\n=== Component Tests ===', flush=True)
        c_ok, c_fail, _ = self.run_component(verbosity=verbosity)
        print('\n=== Stress Tests ===', flush=True)
        s_summary, s_fail = self.run_stress(
            total=stress_total,
            workers=stress_workers,
            sources=stress_sources,
            progress=progress,
            core_backend=core_backend,
            require_rust=require_rust,
            header_probe_rate=header_probe_rate,
            batch_size=batch_size,
            processes=processes,
            threads_per_process=threads_per_process,
            chain_mode=chain_mode,
        )
        report = {
            'component': {'ok': c_ok, 'fail': c_fail},
            'stress': s_summary,
            'overall_fail': c_fail + s_fail,
        }
        return report

    # ------------------------------------------------------------------ #
    #  Plugin CLI integration                                              #
    # ------------------------------------------------------------------ #

    def get_cli_commands(self):
        """Expose test sub-commands to ServiceManager.dispatch_plugin_cli()."""

        def _add_stress_common_args(parser, *, include_core_backend=True):
            parser.add_argument('--total', type=int, default=200)
            parser.add_argument('--workers', type=int, default=8)
            parser.add_argument('--sources', type=int, default=6)
            parser.add_argument('--no-progress', action='store_true', default=False)
            if include_core_backend:
                parser.add_argument('--core-backend', dest='core_backend', default=None,
                                   choices=['pycore', 'rscore'],
                                   help='Core plugin to use (pycore/rscore)')
            parser.add_argument('--require-rust', action='store_true', default=False,
                               help='Fail if core-backend=rscore but os_rscore DLL is unavailable')
            parser.add_argument('--header-probe-rate', type=float, default=0.0,
                               help='Optional packet-header probe sample rate [0.0-1.0]')
            parser.add_argument('--batch-size', type=int, default=1,
                               help='Tasks per future (higher values reduce scheduler overhead)')
            parser.add_argument('--processes', type=int, default=1,
                               help='Number of processes (1 = thread-only mode)')
            parser.add_argument('--threads-per-process', type=int, default=None,
                               help='Thread count inside each process (default: --workers)')
            parser.add_argument('--chain-mode', choices=['core', 'e2e'], default='core',
                               help='Stress chain mode: core=standardize/compress/fuse, e2e=send->receive->process loopback')

        def _log_and_output(suite_name, ok, fail, payload):
            os_log.log_with_const('info', LogMsg.PLUGIN_TEST_RESULT,
                                  plugin='test_plugin', suite=suite_name, ok=ok, fail=fail)
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0 if fail == 0 else 1

        def _write_json_out(path_value, payload, label='saved:'):
            if not path_value:
                return None
            out_path = Path(path_value).expanduser()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
            print('{} {}'.format(label, str(out_path)))
            return out_path

        def _stress_kwargs(ns, *, backend=None, progress_override=None, require_rust_override=None):
            selected_backend = backend if backend is not None else ns.core_backend
            if require_rust_override is None:
                required = bool(ns.require_rust)
            else:
                required = bool(require_rust_override)
            return {
                'total': ns.total,
                'workers': ns.workers,
                'sources': ns.sources,
                'progress': (not ns.no_progress) if progress_override is None else bool(progress_override),
                'core_backend': selected_backend,
                'require_rust': required,
                'header_probe_rate': ns.header_probe_rate,
                'batch_size': ns.batch_size,
                'processes': ns.processes,
                'threads_per_process': ns.threads_per_process,
                'chain_mode': ns.chain_mode,
            }

        def _parse_int_csv(raw, fallback):
            if raw is None:
                return list(fallback)
            text = str(raw).strip()
            if not text:
                return list(fallback)
            values = []
            for token in text.split(','):
                part = token.strip()
                if not part:
                    continue
                values.append(max(1, int(part)))
            return values if values else list(fallback)

        def _print_stress_brief(summary):
            if not isinstance(summary, dict):
                return
            mode = str(summary.get('execution_mode', 'thread'))
            core = str(summary.get('core_backend', 'unknown'))
            pps = float(summary.get('throughput_pps', 0.0) or 0.0)
            lat_values = summary_latency_values(summary)
            fail = int(summary.get('fail', 0) or 0)
            proc = int(summary.get('processes', 1) or 1)
            tpp = int(summary.get('threads_per_process', 1) or 1)
            bsz = int(summary.get('batch_size', 1) or 1)
            print(
                '[stress:brief] core={} mode={} p={} tpp={} b={} pps={:.1f} avg_ms={:.4f} p95_ms={:.4f} p99_ms={:.4f} p99_9_ms={:.4f} p99_99_ms={:.4f} fail={}'.format(
                    core,
                    mode,
                    proc,
                    tpp,
                    bsz,
                    pps,
                    lat_values['avg_latency_ms'],
                    lat_values['p95_latency_ms'],
                    lat_values['p99_latency_ms'],
                    lat_values['p99_9_latency_ms'],
                    lat_values['p99_99_latency_ms'],
                    fail,
                ),
                flush=True,
            )

        def _component(argv):
            import argparse
            p = argparse.ArgumentParser(prog='test_plugin component')
            p.add_argument('--verbosity', type=int, default=1)
            p.add_argument('--parallel', action='store_true', default=False,
                           help='Run test classes concurrently')
            p.add_argument('--processes', type=int, default=0,
                           help='>0: run N classes in parallel OS processes; '
                                '0 (default): use threads when --parallel is set')
            p.add_argument('--max-class-workers', type=int, default=None,
                           help='Max concurrent workers for parallel runner')
            ns = p.parse_args(argv)
            try:
                if ns.parallel or ns.processes > 0:
                    ok, fail, _ = self.run_component_parallel(
                        verbosity=ns.verbosity,
                        max_class_workers=ns.max_class_workers or (ns.processes if ns.processes > 0 else None),
                        use_processes=(ns.processes > 0),
                    )
                else:
                    ok, fail, _ = self.run_component(verbosity=ns.verbosity)
            except KeyboardInterrupt:
                print('\n[component] aborted by user', file=sys.stderr, flush=True)
                return 130
            os_log.log_with_const('info', LogMsg.PLUGIN_TEST_RESULT,
                                  plugin='test_plugin', suite='component', ok=ok, fail=fail)
            print(json.dumps({'ok': ok, 'fail': fail}, ensure_ascii=False))
            return 0 if fail == 0 else 1

        def _stress(argv):
            import argparse

            p = argparse.ArgumentParser(prog='test_plugin stress')
            _add_stress_common_args(p)
            p.add_argument('--auto-profile', action='store_true', default=False,
                           help='Scan candidate concurrency combos first, then run final stress with best config')
            p.add_argument('--profile-total', type=int, default=100000,
                           help='Per-candidate workload used in auto-profile scan')
            p.add_argument('--profile-runs', type=int, default=1,
                           help='Measured scan runs for each auto-profile candidate')
            p.add_argument('--final-runs', type=int, default=1,
                           help='Measured final runs after selecting best candidate')
            p.add_argument('--profile-processes', default='1,2,4,8',
                           help='Candidate process counts (CSV), e.g. 1,2,4,8')
            p.add_argument('--profile-threads', default=None,
                           help='Candidate per-process threads (CSV), default derived from --workers')
            p.add_argument('--profile-batches', default='32,64,128',
                           help='Candidate batch sizes (CSV)')
            p.add_argument('--json-out', dest='json_out', default=None,
                           help='Optional output path for stress/auto-profile JSON report')
            ns = p.parse_args(argv)

            try:
                if ns.auto_profile:
                    process_candidates = _parse_int_csv(ns.profile_processes, [1, 2, 4, 8])
                    thread_default = [max(1, int(ns.workers))]
                    thread_candidates = _parse_int_csv(ns.profile_threads, thread_default)
                    batch_candidates = _parse_int_csv(ns.profile_batches, [32, 64, 128])
                    report = self.run_auto_profile(
                        total=ns.total,
                        workers=ns.workers,
                        sources=ns.sources,
                        core_backend=ns.core_backend,
                        require_rust=ns.require_rust,
                        header_probe_rate=ns.header_probe_rate,
                        profile_total=ns.profile_total,
                        profile_runs=ns.profile_runs,
                        final_runs=ns.final_runs,
                        process_candidates=process_candidates,
                        thread_candidates=thread_candidates,
                        batch_candidates=batch_candidates,
                        batch_size=ns.batch_size,
                        progress=not ns.no_progress,
                        chain_mode=ns.chain_mode,
                    )
                    _write_json_out(ns.json_out, report)
                    final_agg = (report.get('final') or {}).get('aggregate') or {}
                    os_log.log_with_const(
                        'info', LogMsg.PLUGIN_TEST_RESULT,
                        plugin='test_plugin', suite='stress-auto-profile',
                        ok=final_agg.get('ok', 0), fail=final_agg.get('fail', 0),
                    )
                    print(json.dumps(report, indent=2, ensure_ascii=False))
                    return 0 if int(final_agg.get('fail', 0) or 0) == 0 else 1

                summary, fail = self.run_stress(
                    **_stress_kwargs(ns),
                )
                _write_json_out(ns.json_out, summary)
                _print_stress_brief(summary)
                return _log_and_output('stress', summary.get('ok', 0), fail, summary)
            except KeyboardInterrupt:
                print('\n[stress] aborted by user', file=sys.stderr, flush=True)
                return 130

        def _all(argv):
            import argparse
            p = argparse.ArgumentParser(prog='test_plugin all')
            p.add_argument('--verbosity', type=int, default=1)
            _add_stress_common_args(p, include_core_backend=True)
            ns = p.parse_args(argv)
            try:
                report = self.run_all(
                    stress_total=ns.total,
                    stress_workers=ns.workers,
                    stress_sources=ns.sources,
                    verbosity=ns.verbosity,
                    progress=not ns.no_progress,
                    core_backend=ns.core_backend,
                    require_rust=ns.require_rust,
                    header_probe_rate=ns.header_probe_rate,
                    batch_size=ns.batch_size,
                    processes=ns.processes,
                    threads_per_process=ns.threads_per_process,
                    chain_mode=ns.chain_mode,
                )
            except KeyboardInterrupt:
                print('\n[all] aborted by user', file=sys.stderr, flush=True)
                return 130
            print(json.dumps(report, indent=2, ensure_ascii=False))
            return 0 if report['overall_fail'] == 0 else 1

        def _compare(argv):
            """Run stress tests on both backends and print aggregated comparison."""
            import argparse

            p = argparse.ArgumentParser(prog='test_plugin compare')
            p.add_argument('--runs', type=int, default=1,
                           help='Number of measured runs per backend (default: 1)')
            p.add_argument('--warmup', type=int, default=0,
                           help='Warmup runs per backend before measured runs')
            p.add_argument('--json-out', dest='json_out', default=None,
                           help='Optional output path to save comparison JSON')
            _add_stress_common_args(p)
            ns = p.parse_args(argv)

            runs = max(1, int(ns.runs))
            warmup = max(0, int(ns.warmup))

            def _collect_backend(backend):
                series = []
                for idx in range(warmup):
                    print('[warmup][{}] {}/{}'.format(backend, idx + 1, warmup), flush=True)
                    self.run_stress(**_stress_kwargs(
                        ns,
                        backend=backend,
                        progress_override=False,
                        require_rust_override=(backend == 'rscore' and bool(ns.require_rust)),
                    ))
                for idx in range(runs):
                    print('[run][{}] {}/{}'.format(backend, idx + 1, runs), flush=True)
                    summary, fail = self.run_stress(**_stress_kwargs(
                        ns,
                        backend=backend,
                        progress_override=not ns.no_progress,
                        require_rust_override=(backend == 'rscore' and bool(ns.require_rust)),
                    ))
                    summary['fail'] = fail
                    series.append(summary)
                return series

            def _aggregate(series):
                if not series:
                    return {'error': 'no-runs'}

                first = series[0]
                hp = aggregate_header_probe(series)
                out = aggregate_run_series(series, suffix='_avg')
                out.update({
                    'total': int(first.get('total', 0) or 0),
                    'codec_class': first.get('codec_class', 'unknown'),
                    'header_probe_parse_hit_rate': hp['parse_hit_rate'],
                    'core_backend': first.get('core_backend', 'unknown'),
                    'samples': series,
                })
                # Ensure compare output keeps the exact worst-latency key semantics.
                out['max_latency_ms_worst'] = series_max(series, 'max_latency_ms')
                return out

            results = {}
            try:
                for backend in ('pycore', 'rscore'):
                    print('\n--- {} ---'.format(backend), flush=True)
                    try:
                        results[backend] = _aggregate(_collect_backend(backend))
                    except KeyboardInterrupt:
                        raise
                    except Exception as exc:
                        if backend == 'rscore' and not ns.require_rust:
                            results[backend] = {'skipped': True, 'reason': str(exc)}
                        else:
                            results[backend] = {'error': str(exc)}
            except KeyboardInterrupt:
                print('\n[compare] aborted by user – printing partial results…',
                      file=sys.stderr, flush=True)
                if not results:
                    return 130

            print('\n+----------------------------------------------+')
            print('|              Backend Comparison              |')
            print('+--------------------------------------+-----------+-----------+')
            print('| Metric                               | pycore    | rscore    |')
            print('+--------------------------------------+-----------+-----------+')
            fields = [
                ('throughput_pps_avg', 'Throughput avg (pps)'),
                ('avg_latency_ms_avg', 'Avg latency avg (ms)'),
                ('p95_latency_ms_avg', 'P95 latency avg (ms)'),
                ('p99_latency_ms_avg', 'P99 latency avg (ms)'),
                ('p99_9_latency_ms_avg', 'P99.9 latency avg (ms)'),
                ('p99_99_latency_ms_avg', 'P99.99 latency avg (ms)'),
                ('max_latency_ms_worst', 'Worst max latency (ms)'),
                ('codec_class',     'Codec class'),
                ('header_probe_parse_hit_rate', 'Header parse hit rate'),
                ('runs',            'Measured runs'),
                ('skipped',         'Skipped'),
                ('fail',            'Failures'),
            ]
            for key, label in fields:
                py_val = results.get('pycore', {}).get(key, 'n/a')
                rs_val = results.get('rscore', {}).get(key, 'n/a')
                print('| {:<36s} | {:<9s} | {:<9s} |'.format(
                    label, str(py_val)[:9], str(rs_val)[:9]))
            print('+--------------------------------------+-----------+-----------+')

            # speedup
            try:
                py_pps = float(results['pycore'].get('throughput_pps_avg', 0) or 0)
                rs_pps = float(results['rscore'].get('throughput_pps_avg', 0) or 0)
                if py_pps > 0:
                    print('rscore speedup: {:.3f}x'.format(rs_pps / py_pps))
            except Exception:
                pass

            _write_json_out(ns.json_out, results)

            print(json.dumps(results, indent=2, ensure_ascii=False))
            any_fail = any(v.get('fail', 0) > 0 or 'error' in v for v in results.values())
            return 1 if any_fail else 0

        def _full_load(argv):
            """Full-CPU-saturation stress test suite."""
            import argparse
            p = argparse.ArgumentParser(prog='test_plugin full_load')
            p.add_argument('--total', type=int, default=1000000,
                           help='Total iterations for the full-load stress run')
            p.add_argument('--sources', type=int, default=6)
            p.add_argument('--no-progress', action='store_true', default=False)
            p.add_argument('--core-backend', dest='core_backend', default=None,
                           choices=['pycore', 'rscore'])
            p.add_argument('--require-rust', action='store_true', default=False)
            p.add_argument('--header-probe-rate', type=float, default=0.0)
            p.add_argument('--workers-hint', type=int, default=None,
                           help='Override auto-detected process count')
            p.add_argument('--threads-hint', type=int, default=None,
                           help='Override auto-detected threads-per-process')
            p.add_argument('--batch-hint', type=int, default=None,
                           help='Override auto-detected batch size')
            p.add_argument('--with-component', action='store_true', default=False,
                           help='Also run component tests in parallel before the stress run')
            p.add_argument('--verbosity', type=int, default=1)
            p.add_argument('--json-out', dest='json_out', default=None,
                           help='Optional path to write the full-load report JSON')
            ns = p.parse_args(argv)

            report: dict = {'mode': 'full_load'}
            component_fail = 0
            stress_fail = 0

            try:
                # Optional parallel component pre-flight
                if ns.with_component:
                    print('\n=== Component Tests (parallel) ===', flush=True)
                    c_ok, c_fail, _ = self.run_component_parallel(verbosity=ns.verbosity)
                    report['component'] = {'ok': c_ok, 'fail': c_fail}
                    print('component ok={} fail={}'.format(c_ok, c_fail), flush=True)
                    component_fail = c_fail

                print('\n=== Full-Load Stress ===', flush=True)
                summary, fail = self.run_full_load(
                    total=ns.total,
                    sources=ns.sources,
                    core_backend=ns.core_backend,
                    require_rust=ns.require_rust,
                    header_probe_rate=ns.header_probe_rate,
                    progress=not ns.no_progress,
                    workers_hint=ns.workers_hint,
                    threads_hint=ns.threads_hint,
                    batch_hint=ns.batch_hint,
                )
                _print_stress_brief(summary)
                report['stress'] = summary
                stress_fail = fail
                report['overall_fail'] = component_fail + stress_fail
            except KeyboardInterrupt:
                print('\n[full_load] aborted by user – printing partial report…',
                      file=sys.stderr, flush=True)
                report.setdefault('stress', {})
                report['interrupted'] = True
                report['overall_fail'] = component_fail
                if ns.json_out:
                    _write_json_out(ns.json_out, report, label='saved (partial):')
                print(json.dumps(report, indent=2, ensure_ascii=False))
                return 130

            _write_json_out(ns.json_out, report)
            return _log_and_output('full_load', summary.get('ok', 0), report['overall_fail'], report)

        def _integration(argv):
            """Run integration tests."""
            import argparse
            p = argparse.ArgumentParser(prog='test_plugin integration')
            ns = p.parse_args(argv)
            try:
                ok, fail, _ = self.run_integration()
            except KeyboardInterrupt:
                print('\n[integration] aborted by user', file=sys.stderr, flush=True)
                return 130
            os_log.log_with_const('info', LogMsg.PLUGIN_TEST_RESULT,
                                  plugin='test_plugin', suite='integration', ok=ok, fail=fail)
            print(json.dumps({'ok': ok, 'fail': fail}, ensure_ascii=False))
            return 0 if fail == 0 else 1

        def _audit(argv):
            """Run driver capability audit."""
            import argparse
            p = argparse.ArgumentParser(prog='test_plugin audit')
            ns = p.parse_args(argv)
            try:
                complete, incomplete, _ = self.run_audit()
            except KeyboardInterrupt:
                print('\n[audit] aborted by user', file=sys.stderr, flush=True)
                return 130
            os_log.log_with_const('info', LogMsg.PLUGIN_TEST_RESULT,
                                  plugin='test_plugin', suite='audit', ok=complete, fail=incomplete)
            print(json.dumps({'complete': complete, 'incomplete': incomplete}, ensure_ascii=False))
            return 0 if incomplete == 0 else 1

        return {
            'component': _component,
            'stress': _stress,
            'all': _all,
            'compare': _compare,
            'full_load': _full_load,
            'integration': _integration,
            'audit': _audit,
        }

    def run_integration(self):
        """Run integration test suite. Returns (ok_count, fail_count, result_dict)."""
        from opensynaptic.services.test_plugin.integration_test import run_tests
        from pathlib import Path
        repo_root = Path(__file__).resolve().parents[3]
        result = run_tests(repo_root)
        ok = result.get('passed', 0)
        fail = result.get('failed', 0)
        return ok, fail, result
    
    def run_audit(self):
        """Run driver capability audit. Returns (complete_count, incomplete_count, result_dict)."""
        from opensynaptic.services.test_plugin.audit_driver_capabilities import audit_all_drivers
        all_results = audit_all_drivers()
        
        total_complete = 0
        total_incomplete = 0
        total_error = 0
        
        for layer, results in all_results.items():
            for r in results:
                if "error" in r:
                    total_error += 1
                elif r["status"].startswith("✓"):
                    total_complete += 1
                else:
                    total_incomplete += 1
        
        return total_complete, total_incomplete, all_results
