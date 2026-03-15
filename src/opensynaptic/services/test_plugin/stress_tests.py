"""
stress_tests.py – Concurrent transmit / pipeline stress tests for OpenSynaptic.

Run via:
    python -u src/main.py plugin-test --suite stress --workers 8 --total 200
"""
import json
import math
import sys
import time
import threading
import statistics
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, cast

# Ensure package is importable when run directly
_ROOT = None
for _p in Path(__file__).resolve().parents:
    if (_p / 'Config.json').exists():
        _ROOT = str(_p)
        break
if _ROOT and str(Path(_ROOT) / 'src') not in sys.path:
    sys.path.insert(0, str(Path(_ROOT) / 'src'))
if _ROOT and _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from opensynaptic.utils.c.native_loader import has_native_library

import os as _os


def _init_worker_ignore_sigint():
    """Worker-process initializer: suppress SIGINT so the parent handles Ctrl+C.

    Called as the ``initializer`` argument of every ``ProcessPoolExecutor``
    created in this module.  Without this, pressing Ctrl+C sends SIGINT to the
    whole process group, which causes child processes to raise ``KeyboardInterrupt``
    independently and can produce garbled output or hung pools.
    """
    import signal
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (OSError, ValueError):
        pass  # Windows / restricted environments – safe to ignore


def _run_test_class_subprocess(cls_name: str, config_path: str | None = None) -> dict[str, Any]:
    """Picklable subprocess entrypoint: run a single test class and return a result dict.

    Suitable for use with ``ProcessPoolExecutor``.  Each child process imports
    the test suite independently so tests are fully isolated.
    """
    import io
    import sys
    import unittest
    from pathlib import Path

    _root = None
    for _p in Path(__file__).resolve().parents:
        if (_p / 'Config.json').exists():
            _root = str(_p)
            break
    if _root:
        src = str(Path(_root) / 'src')
        if src not in sys.path:
            sys.path.insert(0, src)
        if _root not in sys.path:
            sys.path.insert(0, _root)

    from opensynaptic.services.test_plugin.component_tests import build_suite
    class_map: dict[str, list] = {}
    for test in build_suite():
        class_map.setdefault(type(test).__name__, []).append(test)

    tests = class_map.get(cls_name)
    if not tests:
        return {'cls': cls_name, 'ok': 0, 'fail': 0, 'ran': 0,
                'errors': ['class not found: {}'.format(cls_name)], 'output': ''}

    stream = io.StringIO()
    suite = unittest.TestSuite(tests)
    runner = unittest.TextTestRunner(verbosity=1, stream=stream)
    result = runner.run(suite)
    ok_n = result.testsRun - len(result.failures) - len(result.errors)
    fail_n = len(result.failures) + len(result.errors)
    err_msgs = ['{}:\n{}'.format(str(tc), msg) for tc, msg in result.failures + result.errors]
    return {
        'cls': cls_name,
        'ok': ok_n,
        'fail': fail_n,
        'ran': result.testsRun,
        'errors': err_msgs,
        'output': stream.getvalue(),
    }


def get_full_load_config(
    workers_hint: int | None = None,
    threads_hint: int | None = None,
    batch_hint: int | None = None,
) -> dict[str, Any]:
    """Return an auto-detected concurrency config that saturates all logical CPUs.

    Uses ``os.cpu_count()`` as the process count and distributes threads per
    process evenly.  Any dimension can be overridden via the ``*_hint`` params.

    Keys returned: processes, threads_per_process, workers, batch_size, cpu_count
    """
    cpu = max(1, int(_os.cpu_count() or 4))
    processes = max(1, int(workers_hint or cpu))
    tpp = max(1, int(threads_hint or max(2, (cpu + processes - 1) // processes)))
    batch = max(1, int(batch_hint or 128))
    return {
        'processes': processes,
        'threads_per_process': tpp,
        'workers': tpp,
        'batch_size': batch,
        'cpu_count': cpu,
    }


def _process_worker_run_stress(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Process entrypoint: run one threaded stress shard and return summary dict."""
    # Each child process keeps an independent node/core/runtime cache.
    _, summary = run_stress(**kwargs)
    return summary


def _weighted_avg(pairs):
    num = 0.0
    den = 0.0
    for value, weight in pairs:
        w = max(0.0, float(weight or 0.0))
        if w <= 0:
            continue
        den += w
        num += float(value or 0.0) * w
    return (num / den) if den > 0 else 0.0


def _aggregate_process_summaries(
    summaries: list[dict[str, Any]],
    elapsed_s: float,
    requested_core: str = 'auto',
    processes: int = 1,
    threads_per_process: int = 1,
) -> dict[str, Any]:
    """Merge child-process stress summaries into one report.

    p95 values are merged as weighted averages of child p95s (approximation).
    """
    if not summaries:
        return {
            'total': 0,
            'ok': 0,
            'fail': 0,
            'avg_latency_ms': 0.0,
            'p95_latency_ms': 0.0,
            'min_latency_ms': 0.0,
            'max_latency_ms': 0.0,
            'stage_timing_ms': {
                'standardize_ms': {'avg': 0.0, 'p95': 0.0, 'min': 0.0, 'max': 0.0},
                'compress_ms': {'avg': 0.0, 'p95': 0.0, 'min': 0.0, 'max': 0.0},
                'fuse_ms': {'avg': 0.0, 'p95': 0.0, 'min': 0.0, 'max': 0.0},
            },
            'error_samples': [],
            'elapsed_s': round(float(elapsed_s or 0.0), 3),
            'throughput_pps': 0.0,
            'requested_core': requested_core,
            'execution_mode': 'hybrid',
            'processes': int(processes),
            'threads_per_process': int(threads_per_process),
        }

    total = int(sum(int(s.get('total', 0) or 0) for s in summaries))
    ok = int(sum(int(s.get('ok', 0) or 0) for s in summaries))
    fail = int(sum(int(s.get('fail', 0) or 0) for s in summaries))
    weights = [int(s.get('total', 0) or 0) for s in summaries]

    stage_keys = ('standardize_ms', 'compress_ms', 'fuse_ms')
    stage_stats = {}
    for key in stage_keys:
        avg_val = _weighted_avg((s.get('stage_timing_ms', {}).get(key, {}).get('avg', 0.0), w) for s, w in zip(summaries, weights))
        p95_val = _weighted_avg((s.get('stage_timing_ms', {}).get(key, {}).get('p95', 0.0), w) for s, w in zip(summaries, weights))
        mins = [float(s.get('stage_timing_ms', {}).get(key, {}).get('min', 0.0) or 0.0) for s in summaries]
        maxs = [float(s.get('stage_timing_ms', {}).get(key, {}).get('max', 0.0) or 0.0) for s in summaries]
        stage_stats[key] = {
            'avg': round(avg_val, 4),
            'p95': round(p95_val, 4),
            'min': round(min(mins) if mins else 0.0, 4),
            'max': round(max(maxs) if maxs else 0.0, 4),
        }

    hp_series = [s.get('header_probe') for s in summaries if isinstance(s.get('header_probe'), dict)]
    hp_attempted = int(sum(int(h.get('attempted', 0) or 0) for h in hp_series)) if hp_series else 0
    hp_parsed = int(sum(int(h.get('parsed', 0) or 0) for h in hp_series)) if hp_series else 0
    hp_crc16 = int(sum(int(h.get('crc16_ok', 0) or 0) for h in hp_series)) if hp_series else 0

    first = summaries[0]
    out = {
        'total': total,
        'ok': ok,
        'fail': fail,
        'avg_latency_ms': round(_weighted_avg((s.get('avg_latency_ms', 0.0), w) for s, w in zip(summaries, weights)), 4),
        'p95_latency_ms': round(_weighted_avg((s.get('p95_latency_ms', 0.0), w) for s, w in zip(summaries, weights)), 4),
        'min_latency_ms': round(min(float(s.get('min_latency_ms', 0.0) or 0.0) for s in summaries), 4),
        'max_latency_ms': round(max(float(s.get('max_latency_ms', 0.0) or 0.0) for s in summaries), 4),
        'stage_timing_ms': stage_stats,
        'error_samples': [e for s in summaries for e in (s.get('error_samples') or [])][:5],
        'elapsed_s': round(float(elapsed_s or 0.0), 3),
        'throughput_pps': round((float(total) / float(elapsed_s)) if float(elapsed_s or 0.0) > 0 else 0.0, 1),
        'core_backend': first.get('core_backend', 'unknown'),
        'codec_class': first.get('codec_class', 'unknown'),
        'codec_module': first.get('codec_module', 'unknown'),
        'requested_core': requested_core,
        'execution_mode': 'hybrid',
        'processes': int(processes),
        'threads_per_process': int(threads_per_process),
        'batch_size': int(first.get('batch_size', 1) or 1),
    }
    if hp_series:
        out['header_probe'] = {
            'enabled': True,
            'rate': float(hp_series[0].get('rate', 0.0) or 0.0),
            'parser_available': all(bool(h.get('parser_available', False)) for h in hp_series),
            'attempted': hp_attempted,
            'parsed': hp_parsed,
            'crc16_ok': hp_crc16,
            'parse_hit_rate': round(hp_parsed / hp_attempted, 4) if hp_attempted > 0 else 0.0,
            'crc16_ok_rate': round(hp_crc16 / hp_attempted, 4) if hp_attempted > 0 else 0.0,
        }
    return out


def _make_node(config_path=None, core_name=None):
    from opensynaptic.core import get_core_manager
    manager = get_core_manager()
    selected = str(core_name or '').strip().lower() or manager.get_active_core_name()
    node_cls = manager.get_symbol('OpenSynaptic', name=selected)
    return node_cls(config_path)


def _preflight(core_name=None):
    from opensynaptic.core import get_core_manager
    if not has_native_library('os_base62') or not has_native_library('os_security'):
        raise RuntimeError('Stress suite requires os_base62 and os_security native libraries')
    requested = str(core_name or '').strip().lower()
    manager = get_core_manager()
    if requested and requested not in manager.available_cores():
        raise RuntimeError('unknown core [{}], available={}'.format(requested, manager.available_cores()))
    return {'requested_core': requested or 'auto'}


class StressResult:
    """Aggregated result from a stress run."""

    def __init__(self):
        self.total = 0
        self.ok = 0
        self.fail = 0
        self.errors = []
        self.latencies = []
        self.stage_latencies = {
            'standardize_ms': [],
            'compress_ms': [],
            'fuse_ms': [],
        }
        self._lock = threading.Lock()

    def record_ok(self, latency_ms, stage_ms):
        with self._lock:
            self.total += 1
            self.ok += 1
            self.latencies.append(latency_ms)
            for key in self.stage_latencies:
                self.stage_latencies[key].append(float(stage_ms.get(key, 0.0)))

    def record_fail(self, exc):
        with self._lock:
            self.total += 1
            self.fail += 1
            self.errors.append(str(exc))

    def summary(self) -> dict[str, Any]:
        def _stats(values):
            if not values:
                return {'avg': 0.0, 'p95': 0.0, 'min': 0.0, 'max': 0.0}
            seq = sorted(values)
            idx = min(len(seq) - 1, int(len(seq) * 0.95))
            return {
                'avg': round(sum(values) / len(values), 4),
                'p95': round(seq[idx], 4),
                'min': round(seq[0], 4),
                'max': round(seq[-1], 4),
            }

        stage_stats = {k: _stats(v) for k, v in self.stage_latencies.items()}
        total_stats = _stats(self.latencies)
        return {
            'total': self.total,
            'ok': self.ok,
            'fail': self.fail,
            'avg_latency_ms': total_stats['avg'],
            'p95_latency_ms': total_stats['p95'],
            'min_latency_ms': total_stats['min'],
            'max_latency_ms': total_stats['max'],
            'stage_timing_ms': stage_stats,
            'error_samples': self.errors[:5],
            'core_backend': 'unknown',
            'codec_class': 'unknown',
            'codec_module': 'unknown',
            'requested_core': 'auto',
            'execution_mode': 'thread',
            'processes': 1,
            'threads_per_process': 1,
            'batch_size': 1,
            'header_probe': {
                'enabled': False,
                'rate': 0.0,
                'parser_available': False,
                'attempted': 0,
                'parsed': 0,
                'crc16_ok': 0,
                'parse_hit_rate': 0.0,
                'crc16_ok_rate': 0.0,
            },
        }


def _pipeline_task(node, task_id, sensors, probe_header=False, parse_header_fn=None):
    """Execute one full pipeline (standardize → compress → fuse) without dispatch."""
    t_total_start = time.perf_counter_ns()
    try:
        device_id = f'STRESS_{task_id % 8}'

        t0 = time.perf_counter_ns()
        fact = node.standardizer.standardize(device_id, 'ONLINE', sensors)
        t1 = time.perf_counter_ns()

        compressed = node.engine.compress(fact)
        t2 = time.perf_counter_ns()

        aid = getattr(node, 'assigned_id', 42) or 42
        raw_input = f'{aid};{compressed}'
        pkt = node.fusion.run_engine(raw_input, strategy='FULL')
        t3 = time.perf_counter_ns()

        if not pkt or len(pkt) == 0:
            raise ValueError('Empty packet produced')
        header_probe = None
        if probe_header and callable(parse_header_fn):
            try:
                meta = parse_header_fn(pkt)
                header_probe = {
                    'attempted': True,
                    'parsed': bool(isinstance(meta, dict)),
                    'crc16_ok': bool(meta.get('crc16_ok')) if isinstance(meta, dict) else False,
                }
            except Exception:
                header_probe = {'attempted': True, 'parsed': False, 'crc16_ok': False}
        stage_ms = {
            'standardize_ms': (t1 - t0) / 1_000_000.0,
            'compress_ms': (t2 - t1) / 1_000_000.0,
            'fuse_ms': (t3 - t2) / 1_000_000.0,
        }
        latency_ms = (t3 - t_total_start) / 1_000_000.0
        return latency_ms, stage_ms, None, header_probe
    except Exception as exc:
        return None, None, exc, None


def _progress_line(done, total, started_at, width=28):
    if total <= 0:
        total = 1
    done = max(0, min(done, total))
    ratio = float(done) / float(total)
    filled = int(width * ratio)
    bar = ('#' * filled) + ('-' * (width - filled))
    elapsed = max(0.0, time.monotonic() - started_at)
    rate = (float(done) / elapsed) if elapsed > 0 else 0.0
    eta = ((total - done) / rate) if rate > 0 else 0.0
    return '[{bar}] {done}/{total} {pct:6.2f}% | elapsed={elapsed:7.2f}s | eta={eta:7.2f}s | {rate:8.2f} it/s'.format(
        bar=bar,
        done=done,
        total=total,
        pct=ratio * 100.0,
        elapsed=elapsed,
        eta=eta,
        rate=rate,
    )


def _round4(value: Any) -> float:
    return round(float(value or 0.0), 4)


def _make_candidate_matrix(
    workers: int,
    batch_size: int,
    process_candidates: list[int],
    thread_candidates: list[int],
    batch_candidates: list[int],
) -> list[dict[str, int]]:
    matrix: list[dict[str, int]] = []
    seen = set()
    for proc in process_candidates:
        p = max(1, int(proc or 1))
        if p == 1:
            for b in batch_candidates:
                key = (1, max(1, int(workers)), max(1, int(b or batch_size)))
                if key in seen:
                    continue
                seen.add(key)
                matrix.append({'processes': 1, 'threads_per_process': max(1, int(workers)), 'batch_size': key[2]})
            continue
        for th in thread_candidates:
            for b in batch_candidates:
                key = (p, max(1, int(th or workers)), max(1, int(b or batch_size)))
                if key in seen:
                    continue
                seen.add(key)
                matrix.append({'processes': key[0], 'threads_per_process': key[1], 'batch_size': key[2]})
    return matrix


def _score_candidate(summary: dict[str, Any]) -> tuple[int, float, float, float]:
    fail = int(summary.get('fail', 0) or 0)
    throughput = float(summary.get('throughput_pps', 0.0) or 0.0)
    p95 = float(summary.get('p95_latency_ms', 0.0) or 0.0)
    avg = float(summary.get('avg_latency_ms', 0.0) or 0.0)
    # Sort order: zero-fail first, then higher throughput, then lower p95/avg latency.
    return (1 if fail == 0 else 0, throughput, -p95, -avg)


def _aggregate_series(series: list[dict[str, Any]]) -> dict[str, Any]:
    if not series:
        return {
            'runs': 0,
            'ok': 0,
            'fail': 0,
            'throughput_pps_mean': 0.0,
            'throughput_pps_var': 0.0,
            'throughput_pps_worst': 0.0,
            'avg_latency_ms_mean': 0.0,
            'p95_latency_ms_mean': 0.0,
            'max_latency_ms_worst': 0.0,
        }

    tpps = [float(it.get('throughput_pps', 0.0) or 0.0) for it in series]
    avg_lat = [float(it.get('avg_latency_ms', 0.0) or 0.0) for it in series]
    p95_lat = [float(it.get('p95_latency_ms', 0.0) or 0.0) for it in series]
    max_lat = [float(it.get('max_latency_ms', 0.0) or 0.0) for it in series]

    return {
        'runs': len(series),
        'ok': int(sum(int(it.get('ok', 0) or 0) for it in series)),
        'fail': int(sum(int(it.get('fail', 0) or 0) for it in series)),
        'throughput_pps_mean': _round4(statistics.mean(tpps)),
        'throughput_pps_var': _round4(statistics.pvariance(tpps) if len(tpps) > 1 else 0.0),
        'throughput_pps_worst': _round4(min(tpps) if tpps else 0.0),
        'avg_latency_ms_mean': _round4(statistics.mean(avg_lat) if avg_lat else 0.0),
        'p95_latency_ms_mean': _round4(statistics.mean(p95_lat) if p95_lat else 0.0),
        'max_latency_ms_worst': _round4(max(max_lat) if max_lat else 0.0),
    }


def run_auto_profile(
    total: int,
    workers: int,
    sources: int,
    config_path: str | None = None,
    core_name: str | None = None,
    expect_core: str | None = None,
    expect_codec_class: str | None = None,
    header_probe_rate: float = 0.0,
    profile_total: int = 100000,
    profile_runs: int = 1,
    final_runs: int = 1,
    process_candidates: list[int] | None = None,
    thread_candidates: list[int] | None = None,
    batch_candidates: list[int] | None = None,
    default_batch_size: int = 1,
    progress: bool = True,
) -> dict[str, Any]:
    process_candidates = [max(1, int(x)) for x in (process_candidates or [1, 2, 4, 8])]
    thread_candidates = [max(1, int(x)) for x in (thread_candidates or [max(1, int(workers)), 4, 8])]
    batch_candidates = [max(1, int(x)) for x in (batch_candidates or [max(1, int(default_batch_size)), 32, 64, 128])]
    matrix = _make_candidate_matrix(
        workers=max(1, int(workers)),
        batch_size=max(1, int(default_batch_size)),
        process_candidates=process_candidates,
        thread_candidates=thread_candidates,
        batch_candidates=batch_candidates,
    )

    if not matrix:
        raise RuntimeError('auto-profile generated an empty candidate matrix')

    profile_total = max(1, int(profile_total or 1))
    profile_runs = max(1, int(profile_runs or 1))
    final_runs = max(1, int(final_runs or 1))

    candidates: list[dict[str, Any]] = []
    _scan_interrupted = False
    try:
        for idx, combo in enumerate(matrix, start=1):
            if progress:
                print('[auto-profile][scan] {}/{} -> p={} tpp={} b={}'.format(
                    idx, len(matrix), combo['processes'], combo['threads_per_process'], combo['batch_size']), flush=True)
            samples: list[dict[str, Any]] = []
            for run_idx in range(profile_runs):
                if progress and profile_runs > 1:
                    print('  [scan-run] {}/{}'.format(run_idx + 1, profile_runs), flush=True)
                _, summary = run_stress(
                    total=profile_total,
                    workers=max(1, int(workers)),
                    sources=max(1, int(sources)),
                    config_path=config_path,
                    progress=False,
                    core_name=core_name,
                    expect_core=expect_core,
                    expect_codec_class=expect_codec_class,
                    header_probe_rate=header_probe_rate,
                    batch_size=combo['batch_size'],
                    processes=combo['processes'],
                    threads_per_process=combo['threads_per_process'],
                )
                samples.append(summary)

            aggregate = _aggregate_series(samples)
            representative = dict(samples[-1]) if samples else {}
            representative['throughput_pps'] = aggregate['throughput_pps_mean']
            representative['avg_latency_ms'] = aggregate['avg_latency_ms_mean']
            representative['p95_latency_ms'] = aggregate['p95_latency_ms_mean']
            representative['fail'] = aggregate['fail']
            candidates.append({
                'config': dict(combo),
                'profile_aggregate': aggregate,
                'profile_samples': samples,
                'score_key': _score_candidate(representative),
            })
    except KeyboardInterrupt:
        _scan_interrupted = True
        print('\n[auto-profile] Ctrl+C – scan aborted, using {} candidates so far…'.format(
            len(candidates)), file=sys.stderr, flush=True)
        if not candidates:
            raise

    ranked = sorted(candidates, key=lambda it: it['score_key'], reverse=True)
    for i, item in enumerate(ranked, start=1):
        item['rank'] = i
        item.pop('score_key', None)

    best = ranked[0]
    best_cfg = dict(best.get('config') or {})
    final_series: list[dict[str, Any]] = []
    _final_interrupted = False
    try:
        for run_idx in range(final_runs):
            if progress:
                print('[auto-profile][final] {}/{} -> p={} tpp={} b={}'.format(
                    run_idx + 1,
                    final_runs,
                    best_cfg.get('processes', 1),
                    best_cfg.get('threads_per_process', max(1, int(workers))),
                    best_cfg.get('batch_size', max(1, int(default_batch_size))),
                ), flush=True)
            _, summary = run_stress(
                total=max(1, int(total)),
                workers=max(1, int(workers)),
                sources=max(1, int(sources)),
                config_path=config_path,
                progress=progress,
                core_name=core_name,
                expect_core=expect_core,
                expect_codec_class=expect_codec_class,
                header_probe_rate=header_probe_rate,
                batch_size=int(best_cfg.get('batch_size', max(1, int(default_batch_size)))),
                processes=int(best_cfg.get('processes', 1)),
                threads_per_process=int(best_cfg.get('threads_per_process', max(1, int(workers)))),
            )
            final_series.append(summary)
    except KeyboardInterrupt:
        _final_interrupted = True
        print('\n[auto-profile] Ctrl+C – final runs aborted ({} completed).'.format(
            len(final_series)), file=sys.stderr, flush=True)

    profile_cfg: dict[str, Any] = {
        'profile_total': profile_total,
        'profile_runs': profile_runs,
        'final_total': max(1, int(total)),
        'final_runs': final_runs,
        'workers': max(1, int(workers)),
        'sources': max(1, int(sources)),
        'core_backend': str(core_name or 'auto'),
        'process_candidates': list(process_candidates),
        'thread_candidates': list(thread_candidates),
        'batch_candidates': list(batch_candidates),
    }
    final_report: dict[str, Any] = {
        'config': best_cfg,
        'aggregate': _aggregate_series(final_series),
        'samples': final_series,
    }
    out = cast(dict[str, Any], {
        'mode': 'auto_profile',
        'profile_config': profile_cfg,
        'candidates': ranked,
        'best': best,
        'final': final_report,
    })
    if _scan_interrupted or _final_interrupted:
        out['interrupted'] = True
    return out


def run_stress(total=200, workers=8, sources=6, config_path=None, progress=True,
               core_name=None, expect_core=None, expect_codec_class=None,
               header_probe_rate=0.0, batch_size=1, processes=1,
               threads_per_process=None) -> tuple['StressResult', dict[str, Any]]:
    """
    Run a concurrent pipeline stress test.

    Parameters
    ----------
    total        : int        – total number of encode cycles
    workers      : int        – thread pool size
    sources      : int        – number of distinct sensor configurations (round-robin)
    config_path  : str | None – path to Config.json; None uses ctx auto-detection
    progress     : bool       – print live progress bar
    core_name          : str | None – optional core plugin name passed to CoreManager symbol lookup
    expect_core        : str | None – optional runtime assertion for selected core name
    expect_codec_class : str | None – optional runtime assertion for codec class name
    header_probe_rate  : float      – optional sample rate [0.0, 1.0] for packet header parse probes
    batch_size         : int        – tasks per future; >1 lowers scheduler overhead for very large totals
    processes          : int        – process count (1 = thread-only mode)
    threads_per_process: int | None – per-process thread count in hybrid mode (default=workers)

    Returns
    -------
    (StressResult, summary_dict)
    """
    preflight = _preflight(core_name=core_name)
    process_count = max(1, int(processes or 1))
    per_process_threads = max(1, int(threads_per_process if threads_per_process is not None else workers))

    # Hybrid mode: split work across multiple processes, each running threaded stress.
    if process_count > 1:
        if progress:
            print('[stress] hybrid mode: processes={} threads_per_process={} batch_size={}'.format(
                process_count, per_process_threads, max(1, int(batch_size or 1))), flush=True)
        shard_totals = []
        base = int(total) // process_count
        rem = int(total) % process_count
        for i in range(process_count):
            shard_totals.append(base + (1 if i < rem else 0))

        t_start = time.monotonic()
        child_summaries: list[dict[str, Any]] = []
        completed = [0]
        progress_lock = threading.Lock()

        def _tick_progress():
            if not progress:
                return
            with progress_lock:
                completed[0] += 1
                print('\r' + _progress_line(completed[0], process_count, t_start), end='', flush=True)

        _ppool = ProcessPoolExecutor(
            max_workers=process_count,
            initializer=_init_worker_ignore_sigint,
        )
        _interrupted = False
        _proc_futures: list[Any] = []
        try:
            for shard_total in shard_totals:
                kwargs = {
                    'total': int(shard_total),
                    'workers': int(per_process_threads),
                    'sources': int(sources),
                    'config_path': config_path,
                    'progress': False,
                    'core_name': core_name,
                    'expect_core': expect_core,
                    'expect_codec_class': expect_codec_class,
                    'header_probe_rate': header_probe_rate,
                    'batch_size': batch_size,
                    'processes': 1,
                    'threads_per_process': None,
                }
                _proc_futures.append(_ppool.submit(_process_worker_run_stress, kwargs))

            for f in as_completed(_proc_futures):
                child_summaries.append(f.result())
                _tick_progress()
            # Normal completion – clean shutdown (wait for internal resources).
            _ppool.shutdown(wait=True)
        except KeyboardInterrupt:
            _interrupted = True
            print('\n[stress] Ctrl+C – cancelling child processes…', file=sys.stderr, flush=True)
            for f in _proc_futures:
                f.cancel()
            # KI path – don't block; let OS reclaim resources.
            _ppool.shutdown(wait=False, cancel_futures=True)

        elapsed = time.monotonic() - t_start
        if progress:
            print()
        merged = _aggregate_process_summaries(
            child_summaries,
            elapsed_s=elapsed,
            requested_core=preflight.get('requested_core', 'auto'),
            processes=process_count,
            threads_per_process=per_process_threads,
        )
        if _interrupted:
            merged['interrupted'] = True
        dummy = StressResult()
        dummy.total = int(merged.get('total', 0) or 0)
        dummy.ok = int(merged.get('ok', 0) or 0)
        dummy.fail = int(merged.get('fail', 0) or 0)
        dummy.errors = list(merged.get('error_samples', []) or [])
        return dummy, merged

    node = _make_node(config_path, core_name=core_name)

    # Generic runtime assertions (no backend-specific logic in this module).
    actual_core = type(node).__module__.split('.')[-2] if node else 'unknown'
    codec = getattr(getattr(node, 'engine', None), 'codec', None)
    actual_codec_class = type(codec).__name__ if codec is not None else 'unknown'
    actual_codec_module = type(codec).__module__ if codec is not None else 'unknown'
    if expect_core and actual_core != str(expect_core).strip().lower():
        raise RuntimeError(
            'core expectation failed: actual_core={} expected_core={} (requested_core={})'.format(
                actual_core,
                expect_core,
                preflight.get('requested_core', 'auto'),
            )
        )
    if expect_codec_class and actual_codec_class != str(expect_codec_class).strip():
        raise RuntimeError(
            'codec expectation failed: actual_codec_class={} expected_codec_class={} (codec_module={})'.format(
                actual_codec_class,
                expect_codec_class,
                actual_codec_module,
            )
        )
    # Pre-build sensor sets
    sensor_sets = []
    for i in range(sources):
        sensor_sets.append([
            [f'V{i}', 'OK', float(100 + i * 3), 'Pa'],
            [f'T{i}', 'OK', float(20 + i), 'Cel'],
        ])

    result = StressResult()
    completed = [0]
    progress_lock = threading.Lock()
    progress_state = {'last_print_at': 0.0}

    # Optional Rust/C-native header parser probe (backend-agnostic capability check).
    probe_rate = min(1.0, max(0.0, float(header_probe_rate or 0.0)))
    probe_every = int(math.ceil(1.0 / probe_rate)) if probe_rate > 0.0 else 0
    parse_header_fn = None
    header_parser_available = False
    if probe_every > 0:
        try:
            from opensynaptic.core.rscore.codec import has_header_parser, parse_packet_header
            if has_header_parser():
                parse_header_fn = parse_packet_header
                header_parser_available = True
        except Exception:
            parse_header_fn = None
            header_parser_available = False
    header_probe_stats = {'attempted': 0, 'parsed': 0, 'crc16_ok': 0}

    batch = max(1, int(batch_size or 1))

    def _run_one(idx):
        sensors = sensor_sets[idx % sources]
        do_probe = bool(probe_every > 0 and (idx % probe_every == 0) and callable(parse_header_fn))
        latency, stage_ms, exc, header_probe = _pipeline_task(
            node,
            idx,
            sensors,
            probe_header=do_probe,
            parse_header_fn=parse_header_fn,
        )
        if exc is not None:
            result.record_fail(exc)
        else:
            result.record_ok(latency, stage_ms)
            if header_probe and header_probe.get('attempted'):
                with progress_lock:
                    header_probe_stats['attempted'] += 1
                    if header_probe.get('parsed'):
                        header_probe_stats['parsed'] += 1
                    if header_probe.get('crc16_ok'):
                        header_probe_stats['crc16_ok'] += 1
    def _task_range(start_idx, end_idx):
        for idx in range(start_idx, end_idx):
            _run_one(idx)
        if progress:
            with progress_lock:
                completed[0] += (end_idx - start_idx)
                now = time.monotonic()
                should_print = (completed[0] >= total) or (now - progress_state['last_print_at'] >= 0.10)
                if should_print:
                    print('\r' + _progress_line(completed[0], total, t_start), end='', flush=True)
                    progress_state['last_print_at'] = now

    t_start = time.monotonic()
    _tpool = ThreadPoolExecutor(max_workers=workers)
    _thread_futures: list[Any] = []
    _interrupted = False
    try:
        ranges = []
        i = 0
        while i < total:
            j = min(total, i + batch)
            ranges.append((i, j))
            i = j
        _thread_futures = [_tpool.submit(_task_range, s, e) for (s, e) in ranges]
        for f in as_completed(_thread_futures):
            try:
                f.result()
            except Exception:
                pass
        # Normal completion – wait for thread cleanup.
        _tpool.shutdown(wait=True)
    except KeyboardInterrupt:
        _interrupted = True
        print('\n[stress] Ctrl+C – cancelling thread pool…', file=sys.stderr, flush=True)
        for f in _thread_futures:
            f.cancel()
        _tpool.shutdown(wait=False, cancel_futures=True)
    if progress:
        print()  # newline after progress bar

    elapsed = time.monotonic() - t_start

    summary = cast(dict[str, Any], result.summary())
    summary['elapsed_s'] = round(elapsed, 3)
    summary['throughput_pps'] = round(result.ok / elapsed, 1) if elapsed > 0 else 0.0
    # Record which core / codec was actually used
    summary['core_backend'] = actual_core
    summary['codec_class'] = actual_codec_class
    summary['codec_module'] = actual_codec_module
    summary['requested_core'] = preflight.get('requested_core', 'auto')
    summary['execution_mode'] = 'thread'
    summary['processes'] = 1
    summary['threads_per_process'] = int(workers)
    summary['batch_size'] = batch
    if _interrupted:
        summary['interrupted'] = True
    if probe_every > 0:
        attempted = int(header_probe_stats.get('attempted', 0))
        parsed = int(header_probe_stats.get('parsed', 0))
        crc16_ok = int(header_probe_stats.get('crc16_ok', 0))
        summary['header_probe'] = {
            'enabled': True,
            'rate': probe_rate,
            'parser_available': bool(header_parser_available),
            'attempted': attempted,
            'parsed': parsed,
            'crc16_ok': crc16_ok,
            'parse_hit_rate': round(parsed / attempted, 4) if attempted > 0 else 0.0,
            'crc16_ok_rate': round(crc16_ok / attempted, 4) if attempted > 0 else 0.0,
        }
    return result, summary


if __name__ == '__main__':
    res, summary = run_stress(total=200, workers=8, sources=6)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    sys.exit(0 if res.fail == 0 else 1)

