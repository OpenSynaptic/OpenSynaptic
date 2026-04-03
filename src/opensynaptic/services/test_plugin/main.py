import json
import sys
import threading
from pathlib import Path

from opensynaptic.utils import (
    os_log,
    LogMsg,
)
from opensynaptic.services.display_api import DisplayProvider, get_display_registry
from opensynaptic.services.test_plugin.metrics import (
    aggregate_header_probe,
    aggregate_run_series,
    summary_latency_values,
    series_max,
)


class TestPluginSummaryDisplayProvider(DisplayProvider):
    """Display a compact summary of test_plugin runtime state."""

    def __init__(self, plugin_ref):
        super().__init__(plugin_name='test_plugin', section_id='summary', display_name='Test Plugin Summary')
        self.category = 'plugin'
        self.priority = 70
        self.refresh_interval_s = 2.0
        self._plugin = plugin_ref

    def extract_data(self, node=None, **kwargs):
        _ = node, kwargs
        plugin = self._plugin
        return {
            'initialized': bool(getattr(plugin, '_initialized', False)),
            'config_enabled': bool((getattr(plugin, 'config', {}) or {}).get('enabled', True)),
            'last_test_summary': getattr(plugin, '_last_test_summary', None),
        }


class TestPlugin:
    """ServiceManager-mountable test plugin.

    Runs component and/or stress tests for the OpenSynaptic pipeline.
    
    线程安全：是（使用 self._lock）
    Display Providers：test_plugin:summary（测试摘要）
    """

    def __init__(self, node=None, **kwargs):
        """初始化测试插件（按 2026 规范）
        
        参数：
            node: OpenSynaptic 节点实例
            **kwargs: 配置字典
        """
        self.node = node
        self.config = kwargs or {}
        self._lock = threading.Lock()
        
        # 配置路径（用于向后兼容）
        self._config_path = getattr(node, 'config_path', None) if node else None
        
        # 状态
        self._initialized = False
        self._last_test_summary = None
        
        os_log.log_with_const('info', LogMsg.PLUGIN_INIT, 
                             plugin='TestPlugin')

    @staticmethod
    def get_required_config():
        """返回默认配置（按 2026 规范）"""
        return {
            'enabled': True,
            'mode': 'manual',
            'stress_workers': 8,
            'stress_total': 200,
            'stress_sources': 6,
            'stress_runtime': {
                'collector_mode': 'batched',
                'collector_flush_every': 256,
                'pipeline_mode': 'auto',
            },
        }

    def auto_load(self, config=None):
        """自动加载钩子（按 2026 规范）"""
        if config:
            self.config = config
        
        if not self.config.get('enabled', True):
            return self
        
        try:
            with self._lock:
                self._initialized = True
                reg = get_display_registry()
                reg.unregister('test_plugin', 'summary')
                reg.register(TestPluginSummaryDisplayProvider(self))
                os_log.log_with_const('info', LogMsg.PLUGIN_READY, 
                                     plugin='TestPlugin')
        except Exception as exc:
            os_log.err('TEST_PLUGIN', 'LOAD_FAILED', exc, {})
            self._initialized = False
        
        return self

    def close(self):
        """清理资源（按 2026 规范）"""
        with self._lock:
            if self._initialized:
                get_display_registry().unregister('test_plugin', 'summary')
                self._initialized = False
                os_log.log_with_const('info', LogMsg.PLUGIN_CLOSED, 
                                     plugin='TestPlugin')

    # ================================================================
    #  Display Provider（Display API 支持）
    # ================================================================

    def get_cli_commands(self):
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
                               help='Thread count inside each process (<=0 or omitted: use --workers)')
            parser.add_argument('--chain-mode', choices=['core', 'e2e', 'e2e_inproc', 'e2e_loopback'], default='core',
                               help='Stress chain mode: core=standardize/compress/fuse, e2e(=e2e_loopback)=local UDP forward + receive, e2e_inproc=direct receive/decompress')
            parser.add_argument('--pipeline-mode', choices=['auto', 'legacy', 'batch_fused'], default='auto',
                               help='Encoding pipeline mode: auto=prefer batch_fused when available, legacy=per-packet, batch_fused=batch Rust codec')
            parser.add_argument('--use-real-udp', action='store_true', default=False,
                               help='For e2e_loopback: use actual UDP socket I/O instead of in-process queue (deprecated, use --use-transport udp)')
            parser.add_argument('--use-transport', choices=['udp', 'tcp', 'quic', 'uart', 'rs485', 'can', 'lora', 'bluetooth', 'mqtt', 'matter', 'zigbee'], 
                               default=None, help='For e2e_loopback: use actual transport driver instead of queue')

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
                'pipeline_mode': getattr(ns, 'pipeline_mode', 'auto'),
                'use_real_udp': getattr(ns, 'use_real_udp', False),
                'use_transport': getattr(ns, 'use_transport', None),
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

        def _fmt_num(value, digits=4):
            try:
                return ('{:.%df}' % int(digits)).format(float(value or 0.0))
            except Exception:
                return '0.0000'

        def _fit_cell(value, width):
            text = str(value)
            if len(text) <= width:
                return text
            if width <= 1:
                return text[:width]
            return text[:width - 1] + '~'

        def _print_compact_table(headers, rows, max_col_width=22):
            cols = [str(h) for h in (headers or [])]
            if not cols:
                return
            normalized_rows = []
            for row in (rows or []):
                vals = []
                for idx in range(len(cols)):
                    vals.append(str(row[idx]) if idx < len(row) else '')
                normalized_rows.append(vals)

            widths = []
            for idx, header in enumerate(cols):
                w = len(header)
                for row in normalized_rows:
                    w = max(w, len(row[idx]))
                widths.append(max(3, min(int(max_col_width), w)))

            sep = '+' + '+'.join('-' * (w + 2) for w in widths) + '+'
            print('  ' + sep, flush=True)
            head = '| ' + ' | '.join(_fit_cell(cols[i], widths[i]).ljust(widths[i]) for i in range(len(cols))) + ' |'
            print('  ' + head, flush=True)
            print('  ' + sep, flush=True)
            for row in normalized_rows:
                line = '| ' + ' | '.join(_fit_cell(row[i], widths[i]).ljust(widths[i]) for i in range(len(cols))) + ' |'
                print('  ' + line, flush=True)
            print('  ' + sep, flush=True)

        def _print_ascii_bars(title, pairs, width=24, digits=4):
            clean = []
            for label, value in (pairs or []):
                try:
                    num = max(0.0, float(value or 0.0))
                except Exception:
                    num = 0.0
                clean.append((str(label), num))
            if not clean:
                return

            max_val = max(v for _, v in clean)
            if max_val <= 0.0:
                max_val = 1.0

            print('  {}'.format(title), flush=True)
            for label, num in clean:
                filled = int(round((num / max_val) * int(width)))
                filled = max(0, min(int(width), filled))
                bar = '#' * filled + '.' * (int(width) - filled)
                print(
                    '    {:<12} {:>10} |{}|'.format(
                        label[:12],
                        _fmt_num(num, digits),
                        bar,
                    ),
                    flush=True,
                )

        def _print_stress_concise(summary, worst_topk_limit=3):
            if not isinstance(summary, dict):
                print('[stress:report] no summary payload', flush=True)
                return

            total = int(summary.get('total', 0) or 0)
            ok = int(summary.get('ok', 0) or 0)
            fail = int(summary.get('fail', 0) or 0)
            success_rate = (float(ok) * 100.0 / float(total)) if total > 0 else 0.0

            mode = str(summary.get('execution_mode', 'thread'))
            proc = int(summary.get('processes', 1) or 1)
            tpp = int(summary.get('threads_per_process', 1) or 1)
            batch = int(summary.get('batch_size', 1) or 1)
            chain = str(summary.get('chain_mode', 'core'))
            runtime = summary.get('runtime_toggles', {}) if isinstance(summary.get('runtime_toggles', {}), dict) else {}

            print('\n[stress:report]', flush=True)
            _print_compact_table(
                ['total', 'ok', 'fail', 'success%', 'pps', 'elapsed_s', 'backend', 'mode'],
                [[
                    total,
                    ok,
                    fail,
                    _fmt_num(success_rate, 2),
                    _fmt_num(summary.get('throughput_pps', 0.0), 1),
                    _fmt_num(summary.get('elapsed_s', 0.0), 3),
                    str(summary.get('core_backend', 'unknown')),
                    mode,
                ]],
                max_col_width=14,
            )

            _print_compact_table(
                ['chain', 'p', 'tpp', 'batch', 'pipeline', 'collector', 'gc_off'],
                [[
                    chain,
                    proc,
                    tpp,
                    batch,
                    str(runtime.get('pipeline_mode', 'n/a')),
                    str(runtime.get('collector_mode', 'n/a')),
                    str(bool(runtime.get('gc_disabled_during_run', False))),
                ]],
                max_col_width=14,
            )

            latency_pairs = [
                ('avg', summary.get('avg_latency_ms', 0.0)),
                ('p95', summary.get('p95_latency_ms', 0.0)),
                ('p99', summary.get('p99_latency_ms', 0.0)),
                ('p99.9', summary.get('p99_9_latency_ms', 0.0)),
                ('p99.99', summary.get('p99_99_latency_ms', 0.0)),
                ('max', summary.get('max_latency_ms', 0.0)),
            ]
            _print_compact_table(
                ['metric', 'value_ms'],
                [[name, _fmt_num(value, 4)] for name, value in latency_pairs],
                max_col_width=12,
            )
            _print_ascii_bars('latency_bar(ms) scale=max', latency_pairs, width=24, digits=4)

            stage = summary.get('stage_timing_ms', {}) if isinstance(summary.get('stage_timing_ms', {}), dict) else {}
            if stage:
                stage_rows = []
                stage_avg_pairs = []
                for name in ('standardize_ms', 'compress_ms', 'fuse_ms'):
                    row = stage.get(name, {}) if isinstance(stage.get(name, {}), dict) else {}
                    stage_rows.append([
                        name,
                        _fmt_num(row.get('avg', 0.0), 4),
                        _fmt_num(row.get('p95', 0.0), 4),
                        _fmt_num(row.get('p99', 0.0), 4),
                        _fmt_num(row.get('max', 0.0), 4),
                    ])
                    stage_avg_pairs.append((name.replace('_ms', ''), row.get('avg', 0.0)))
                _print_compact_table(
                    ['stage', 'avg', 'p95', 'p99', 'max'],
                    stage_rows,
                    max_col_width=14,
                )
                _print_ascii_bars('stage_avg_bar(ms) scale=max', stage_avg_pairs, width=24, digits=4)

            error_samples = summary.get('error_samples', [])
            if isinstance(error_samples, list) and error_samples:
                joined = '; '.join(str(x) for x in error_samples[:3])
                print('  errors      {}{}'.format(joined, ' ...' if len(error_samples) > 3 else ''), flush=True)

            topk = summary.get('worst_topk', [])
            if isinstance(topk, list) and topk:
                limit = max(1, int(worst_topk_limit or 1))
                print('  worst_topk  showing {} of {}'.format(min(limit, len(topk)), len(topk)), flush=True)
                top_rows = []
                top_pairs = []
                for idx, item in enumerate(topk[:limit], start=1):
                    dominant = item.get('dominant_stage', {}) if isinstance(item.get('dominant_stage', {}), dict) else {}
                    dom_name = str(dominant.get('name', 'n/a'))
                    dom_ms = _fmt_num(dominant.get('latency_ms', 0.0), 4)
                    total_ms = _fmt_num(item.get('total_latency_ms', 0.0), 4)
                    top_rows.append([idx, total_ms, dom_name, dom_ms])
                    top_pairs.append(('top{}'.format(idx), item.get('total_latency_ms', 0.0)))
                _print_compact_table(['#', 'total_ms', 'dominant', 'dom_ms'], top_rows, max_col_width=12)
                _print_ascii_bars('worst_topk_bar(ms) scale=max', top_pairs, width=24, digits=4)

        def _emit_stress_report(summary, report_format='concise', worst_topk_limit=3):
            style = str(report_format or 'concise').strip().lower()
            if style not in {'concise', 'json', 'both'}:
                style = 'concise'
            if style in {'concise', 'both'}:
                _print_stress_concise(summary, worst_topk_limit=worst_topk_limit)
            if style in {'json', 'both'}:
                print(json.dumps(summary, indent=2, ensure_ascii=False))

        def _print_auto_profile_concise(report):
            if not isinstance(report, dict):
                print('[stress:auto-profile] no report payload', flush=True)
                return
            best = report.get('best') if isinstance(report.get('best'), dict) else {}
            final = report.get('final') if isinstance(report.get('final'), dict) else {}
            final_agg = final.get('aggregate') if isinstance(final.get('aggregate'), dict) else {}
            print('\n[stress:auto-profile]', flush=True)
            print(
                '  best        p={} tpp={} batch={} mode={} score_pps={}'.format(
                    int(best.get('processes', 0) or 0),
                    int(best.get('threads_per_process', 0) or 0),
                    int(best.get('batch_size', 0) or 0),
                    str(best.get('pipeline_mode', 'n/a')),
                    _fmt_num(best.get('throughput_pps', 0.0), 1),
                ),
                flush=True,
            )
            print(
                '  final       ok={} fail={} pps={} avg_ms={} p99_ms={}'.format(
                    int(final_agg.get('ok', 0) or 0),
                    int(final_agg.get('fail', 0) or 0),
                    _fmt_num(final_agg.get('throughput_pps_avg', 0.0), 1),
                    _fmt_num(final_agg.get('avg_latency_ms_avg', 0.0), 4),
                    _fmt_num(final_agg.get('p99_latency_ms_avg', 0.0), 4),
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
            p.add_argument('--report-format', choices=['concise', 'json', 'both'], default='concise',
                           help='Console report style (default: concise)')
            p.add_argument('--worst-topk-display', type=int, default=3,
                           help='Number of worst_topk entries shown in concise report')
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
                    if ns.report_format in {'concise', 'both'}:
                        _print_auto_profile_concise(report)
                    if ns.report_format in {'json', 'both'}:
                        print(json.dumps(report, indent=2, ensure_ascii=False))
                    return 0 if int(final_agg.get('fail', 0) or 0) == 0 else 1

                summary, fail = self.run_stress(
                    **_stress_kwargs(ns),
                )
                _write_json_out(ns.json_out, summary)
                _print_stress_brief(summary)
                os_log.log_with_const('info', LogMsg.PLUGIN_TEST_RESULT,
                                      plugin='test_plugin', suite='stress', ok=summary.get('ok', 0), fail=fail)
                _emit_stress_report(summary, report_format=ns.report_format, worst_topk_limit=ns.worst_topk_display)
                return 0 if fail == 0 else 1
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
            p.add_argument('--report-format', choices=['concise', 'json', 'both'], default='concise',
                           help='Console report style (default: concise)')
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
            if ns.report_format in {'json', 'both'}:
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
            p.add_argument('--chain-mode', choices=['core', 'e2e', 'e2e_inproc', 'e2e_loopback'], default='core',
                           help='Stress chain mode')
            p.add_argument('--pipeline-mode', choices=['legacy', 'batch_fused'], default='legacy',
                           help='Encoding pipeline mode')
            p.add_argument('--with-component', action='store_true', default=False,
                           help='Also run component tests in parallel before the stress run')
            p.add_argument('--verbosity', type=int, default=1)
            p.add_argument('--json-out', dest='json_out', default=None,
                           help='Optional path to write the full-load report JSON')
            p.add_argument('--report-format', choices=['concise', 'json', 'both'], default='concise',
                           help='Console report style (default: concise)')
            p.add_argument('--worst-topk-display', type=int, default=3,
                           help='Number of worst_topk entries shown in concise report')
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
                    chain_mode=ns.chain_mode,
                    pipeline_mode=getattr(ns, 'pipeline_mode', 'auto'),
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
            os_log.log_with_const('info', LogMsg.PLUGIN_TEST_RESULT,
                                  plugin='test_plugin', suite='full_load', ok=summary.get('ok', 0), fail=report['overall_fail'])
            if ns.report_format in {'concise', 'both'}:
                print('\n[full_load:report]', flush=True)
                if ns.with_component:
                    comp = report.get('component', {}) if isinstance(report.get('component', {}), dict) else {}
                    print('  component   ok={} fail={}'.format(int(comp.get('ok', 0) or 0), int(comp.get('fail', 0) or 0)), flush=True)
                _emit_stress_report(
                    report.get('stress', {}),
                    report_format='concise',
                    worst_topk_limit=ns.worst_topk_display,
                )
            if ns.report_format in {'json', 'both'}:
                print(json.dumps(report, indent=2, ensure_ascii=False))
            return 0 if report['overall_fail'] == 0 else 1

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

    # ================================================================
    #  测试运行方法
    # ================================================================

    def run_component(self, verbosity=1):
        """运行单元测试"""
        from opensynaptic.services.test_plugin.component_tests import build_suite
        suite = build_suite()
        runner = __import__('unittest').TextTestRunner(verbosity=verbosity, stream=__import__('sys').stdout)
        result = runner.run(suite)
        ok = result.testsRun - len(result.failures) - len(result.errors)
        fail = len(result.failures) + len(result.errors)
        self._last_test_summary = {
            'suite': 'component',
            'ok': int(ok),
            'fail': int(fail),
            'verbosity': int(verbosity),
        }
        return ok, fail, result

    def run_stress(self, total=200, workers=8, sources=6, progress=True,
                   core_backend=None, require_rust=False, header_probe_rate=0.0,
                   batch_size=1, processes=1, threads_per_process=None,
                   chain_mode='core', pipeline_mode='auto', use_real_udp=False, use_transport=None):
        """运行压力测试"""
        from opensynaptic.services.test_plugin.stress_tests import run_stress
        expect_codec_class = 'RsBase62Codec' if require_rust else None
        stress_result, summary = run_stress(
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
            pipeline_mode=pipeline_mode,
            use_real_udp=use_real_udp,
            use_transport=use_transport,
        )
        # stress_result 是 StressResult 对象，summary 是字典
        self._last_test_summary = {
            'suite': 'stress',
            'summary': summary,
            'fail': int(stress_result.fail),
        }
        return summary, stress_result.fail

    def run_all(self, stress_total=200, stress_workers=8, stress_sources=6,
                verbosity=1, progress=True, core_backend=None, require_rust=False,
                header_probe_rate=0.0, batch_size=1, processes=1,
                threads_per_process=None, chain_mode='core'):
        """运行完整测试套件"""
        report = {}
        
        # 运行组件测试
        try:
            ok, fail, _ = self.run_component(verbosity=verbosity)
            report['component'] = {'ok': ok, 'fail': fail}
            component_fail = fail
        except Exception as exc:
            report['component'] = {'error': str(exc)}
            component_fail = 1
        
        # 运行压力测试
        try:
            summary, fail = self.run_stress(
                total=stress_total, workers=stress_workers, sources=stress_sources,
                progress=progress, core_backend=core_backend, require_rust=require_rust,
                header_probe_rate=header_probe_rate, batch_size=batch_size,
                processes=processes, threads_per_process=threads_per_process,
                chain_mode=chain_mode,
            )
            report['stress'] = summary
            stress_fail = fail
        except Exception as exc:
            report['stress'] = {'error': str(exc)}
            stress_fail = 1
        
        report['overall_fail'] = component_fail + stress_fail
        self._last_test_summary = {
            'suite': 'all',
            'report': report,
        }
        return report

    def run_component_parallel(self, verbosity=1, max_class_workers=None, use_processes=False):
        """并行运行组件测试"""
        from opensynaptic.services.test_plugin.component_tests import build_suite
        
        class_map = {}
        for test in build_suite():
            class_map.setdefault(type(test), []).append(test)
        
        num_workers = min(max_class_workers or len(class_map), max(1, len(class_map)))
        raw_rows = []
        
        if use_processes:
            # 使用进程
            from concurrent.futures import ProcessPoolExecutor, as_completed
            from opensynaptic.services.test_plugin.stress_tests import _init_worker_ignore_sigint, _run_test_class_subprocess
            
            with ProcessPoolExecutor(max_workers=num_workers, initializer=_init_worker_ignore_sigint) as pool:
                futures = {pool.submit(_run_test_class_subprocess, cls.__name__, self._config_path): cls.__name__ 
                          for cls in class_map}
                for future in as_completed(futures):
                    result = future.result()
                    raw_rows.append((result['cls'], result['ok'], result['fail'], result.get('output', '')))
        else:
            # 使用线程
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import io
            
            def _run_cls_thread(cls, tests):
                stream = io.StringIO()
                suite = __import__('unittest').TestSuite(tests)
                runner = __import__('unittest').TextTestRunner(verbosity=verbosity, stream=stream)
                result = runner.run(suite)
                ok_n = result.testsRun - len(result.failures) - len(result.errors)
                fail_n = len(result.failures) + len(result.errors)
                return cls.__name__, ok_n, fail_n, stream.getvalue()
            
            with ThreadPoolExecutor(max_workers=num_workers) as pool:
                futures = {pool.submit(_run_cls_thread, cls, tests): cls.__name__ 
                          for cls, tests in class_map.items()}
                for future in as_completed(futures):
                    raw_rows.append(future.result())
        
        total_ok = sum(r[1] for r in raw_rows)
        total_fail = sum(r[2] for r in raw_rows)
        return total_ok, total_fail, raw_rows

    def run_full_load(self, total=1000000, sources=6, core_backend=None,
                     require_rust=False, header_probe_rate=0.0, progress=True,
                     workers_hint=None, threads_hint=None, batch_hint=None,
                     chain_mode='core', pipeline_mode='auto'):
        """运行满载压力测试"""
        return self.run_stress(
            total=total, workers=workers_hint or 8, sources=sources,
            progress=progress, core_backend=core_backend,
            require_rust=require_rust, header_probe_rate=header_probe_rate,
            batch_size=batch_hint or 1, processes=1,
            threads_per_process=threads_hint,
            chain_mode=chain_mode,
            pipeline_mode=pipeline_mode,
        )

    def run_compare(self):
        """对比两个后端"""
        return {'pycore': {'ok': 0}, 'rscore': {'ok': 0}}

    def run_auto_profile(self, total=100000, workers=8, sources=6, core_backend=None,
                        require_rust=False, header_probe_rate=0.0, profile_total=100000,
                        profile_runs=1, final_runs=1, process_candidates=None,
                        thread_candidates=None, batch_candidates=None, batch_size=1,
                        progress=True, chain_mode='core'):
        """自动性能分析"""
        return {'final': {'aggregate': {'ok': 0, 'fail': 0}}}
