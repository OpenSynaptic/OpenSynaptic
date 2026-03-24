"""
stress_tests.py – Concurrent transmit / pipeline stress tests for OpenSynaptic.

Run via:
    python -u src/main.py plugin-test --suite stress --workers 8 --total 200
"""
import json
import math
import queue
import sys
import time
import threading
import gc
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, as_completed, wait
from pathlib import Path
from types import SimpleNamespace
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

from opensynaptic.utils import (
    has_native_library,
    read_json,
)
from opensynaptic.services.test_plugin.metrics import (
    PERCENTILE_KEYS,
    aggregate_header_probe,
    aggregate_run_series,
    empty_stage_stats,
    round4,
    stats_from_values,
    weighted_avg,
    weighted_series_value,
)

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
    runner = globals().get('run_stress')
    if not callable(runner):
        from opensynaptic.services.test_plugin.stress_tests import run_stress as runner
    _, summary = runner(**kwargs)
    return summary


def _aggregate_process_summaries(
    summaries: list[dict[str, Any]],
    elapsed_s: float,
    requested_core: str = 'auto',
    processes: int = 1,
    threads_per_process: int = 1,
) -> dict[str, Any]:
    """Merge child-process stress summaries into one report.

    Tail percentiles are merged as weighted averages of child summaries (approximation).
    """
    if not summaries:
        return {
            'total': 0,
            'ok': 0,
            'fail': 0,
            'avg_latency_ms': 0.0,
            'p95_latency_ms': 0.0,
            'p99_latency_ms': 0.0,
            'p99_9_latency_ms': 0.0,
            'p99_99_latency_ms': 0.0,
            'min_latency_ms': 0.0,
            'max_latency_ms': 0.0,
            'stage_timing_ms': empty_stage_stats(),
            'error_samples': [],
            'elapsed_s': round(float(elapsed_s or 0.0), 3),
            'throughput_pps': 0.0,
            'requested_core': requested_core,
            'execution_mode': 'hybrid',
            'processes': int(processes),
            'threads_per_process': int(threads_per_process),
            'chain_mode': 'core',
            'worst_sample': {
                'total_latency_ms': 0.0,
                'task_id': None,
                'chain_mode': 'core',
                'stage_timing_ms': {
                    'standardize_ms': 0.0,
                    'compress_ms': 0.0,
                    'fuse_ms': 0.0,
                },
                'stage_share_pct': {
                    'standardize_ms': 0.0,
                    'compress_ms': 0.0,
                    'fuse_ms': 0.0,
                },
                'dominant_stage': {
                    'name': 'fuse_ms',
                    'latency_ms': 0.0,
                },
            },
            'worst_topk': [],
        }

    total = int(sum(int(s.get('total', 0) or 0) for s in summaries))
    ok = int(sum(int(s.get('ok', 0) or 0) for s in summaries))
    fail = int(sum(int(s.get('fail', 0) or 0) for s in summaries))
    weights = [int(s.get('total', 0) or 0) for s in summaries]

    stage_keys = ('standardize_ms', 'compress_ms', 'fuse_ms')
    stage_stats = {}
    for key in stage_keys:
        stage_entry = {
            'avg': round4(weighted_avg((s.get('stage_timing_ms', {}).get(key, {}).get('avg', 0.0), w) for s, w in zip(summaries, weights))),
        }
        for pct_key, fallback_key, _ in PERCENTILE_KEYS:
            fallback = fallback_key or pct_key
            stage_entry[pct_key] = round4(
                weighted_avg(
                    (s.get('stage_timing_ms', {}).get(key, {}).get(pct_key, s.get('stage_timing_ms', {}).get(key, {}).get(fallback, 0.0)), w)
                    for s, w in zip(summaries, weights)
                )
            )
        mins = [float(s.get('stage_timing_ms', {}).get(key, {}).get('min', 0.0) or 0.0) for s in summaries]
        maxs = [float(s.get('stage_timing_ms', {}).get(key, {}).get('max', 0.0) or 0.0) for s in summaries]
        stage_entry['min'] = round4(min(mins) if mins else 0.0)
        stage_entry['max'] = round4(max(maxs) if maxs else 0.0)
        stage_stats[key] = stage_entry

    hp_series = [s.get('header_probe') for s in summaries if isinstance(s.get('header_probe'), dict)]
    hp_stats = aggregate_header_probe(cast(list[dict[str, Any]], hp_series)) if hp_series else {}

    first = summaries[0]
    all_worst: list[dict[str, Any]] = []
    for idx, s in enumerate(summaries):
        entries = s.get('worst_topk') if isinstance(s.get('worst_topk'), list) else None
        if not entries:
            cand = s.get('worst_sample') if isinstance(s.get('worst_sample'), dict) else None
            entries = [cand] if cand else []
        for item in entries:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            row['process_index'] = idx
            all_worst.append(row)
    all_worst.sort(key=lambda it: float(it.get('total_latency_ms', 0.0) or 0.0), reverse=True)
    topk_worst = all_worst[:5]
    best_worst = topk_worst[0] if topk_worst else None

    out = {
        'total': total,
        'ok': ok,
        'fail': fail,
        'avg_latency_ms': round4(weighted_series_value(summaries, weights, 'avg_latency_ms')),
        'p95_latency_ms': round4(weighted_series_value(summaries, weights, 'p95_latency_ms')),
        'p99_latency_ms': round4(weighted_series_value(summaries, weights, 'p99_latency_ms', fallback_key='p95_latency_ms')),
        'p99_9_latency_ms': round4(weighted_series_value(summaries, weights, 'p99_9_latency_ms', fallback_key='p95_latency_ms')),
        'p99_99_latency_ms': round4(weighted_series_value(summaries, weights, 'p99_99_latency_ms', fallback_key='p95_latency_ms')),
        'min_latency_ms': round4(min(float(s.get('min_latency_ms', 0.0) or 0.0) for s in summaries)),
        'max_latency_ms': round4(max(float(s.get('max_latency_ms', 0.0) or 0.0) for s in summaries)),
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
        'chain_mode': str(first.get('chain_mode', 'core') or 'core'),
        'runtime_toggles': dict(first.get('runtime_toggles') or {}),
        'worst_sample': best_worst or {
            'total_latency_ms': round4(max(float(s.get('max_latency_ms', 0.0) or 0.0) for s in summaries)),
            'task_id': None,
            'chain_mode': str(first.get('chain_mode', 'core') or 'core'),
            'stage_timing_ms': {'standardize_ms': 0.0, 'compress_ms': 0.0, 'fuse_ms': 0.0},
            'stage_share_pct': {'standardize_ms': 0.0, 'compress_ms': 0.0, 'fuse_ms': 0.0},
            'dominant_stage': {'name': 'fuse_ms', 'latency_ms': 0.0},
        },
        'worst_topk': topk_worst,
    }
    if hp_series:
        out['header_probe'] = {
            'enabled': True,
            'rate': float(hp_series[0].get('rate', 0.0) or 0.0),
            'parser_available': all(bool(h.get('parser_available', False)) for h in hp_series),
            'attempted': int(hp_stats.get('attempted', 0) or 0),
            'parsed': int(hp_stats.get('parsed', 0) or 0),
            'crc16_ok': int(hp_stats.get('crc16_ok', 0) or 0),
            'parse_hit_rate': float(hp_stats.get('parse_hit_rate', 0.0) or 0.0),
            'crc16_ok_rate': float(hp_stats.get('crc16_ok_rate', 0.0) or 0.0),
        }
    return out


def _make_node(config_path=None, core_name=None):
    from opensynaptic.core import get_core_manager
    manager = get_core_manager()
    # Keep stress workers aligned with CLI node creation: config-backed core selection
    # must use config_path (or ctx fallback) before resolving OpenSynaptic symbol.
    if config_path:
        try:
            manager.set_config_path(config_path)
        except Exception:
            pass
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


def _resolve_stress_runtime_options(node=None, config_path=None) -> dict[str, Any]:
    """Resolve internal stress-runtime toggles from Config.json.

    This keeps CLI/function contracts stable while allowing layer-internal
    implementation switches.
    """
    cfg = {}
    if node is not None:
        cfg = getattr(node, 'config', {}) or {}
    if not isinstance(cfg, dict) or not cfg:
        cfg = read_json(config_path) if config_path else {}

    plugin_cfg = (((cfg.get('RESOURCES', {}) or {}).get('service_plugins', {}) or {}).get('test_plugin', {}) or {})
    runtime_cfg = plugin_cfg.get('stress_runtime', {}) if isinstance(plugin_cfg, dict) else {}
    if not isinstance(runtime_cfg, dict):
        runtime_cfg = {}

    raw_mode = str(runtime_cfg.get('collector_mode', 'legacy') or 'legacy').strip().lower()
    mode_alias = {
        'legacy': 'legacy',
        'batched': 'batched',
        'thread_local': 'batched',
        'sharded': 'batched',
    }
    mode = mode_alias.get(raw_mode, 'legacy')
    flush_explicit = isinstance(runtime_cfg, dict) and ('collector_flush_every' in runtime_cfg)
    flush_every = max(1, int(runtime_cfg.get('collector_flush_every', 256) or 256))

    raw_pipeline = str(runtime_cfg.get('pipeline_mode', 'legacy') or 'legacy').strip().lower()
    pipeline_alias = {
        'legacy': 'legacy',
        # pre_std is now fully merged into the same batch-fused ABI path.
        'pre_std': 'batch_fused',
        'pre-std': 'batch_fused',
        'batch_fused': 'batch_fused',
        'batch-fused': 'batch_fused',
        'fused': 'batch_fused',
        'batch': 'batch_fused',
    }
    pipeline = pipeline_alias.get(raw_pipeline, 'legacy')

    raw_gc = str(runtime_cfg.get('gc_mode', 'auto') or 'auto').strip().lower()
    gc_mode = raw_gc if raw_gc in {'auto', 'on', 'off'} else 'auto'

    return {
        'collector_mode': mode,
        'collector_flush_every': flush_every,
        'collector_flush_explicit': bool(flush_explicit),
        'pipeline_mode': pipeline,
        'gc_mode': gc_mode,
    }


def _drain_progress_queue(progress_queue, current_done, total):
    if progress_queue is None:
        return current_done
    done = int(current_done)
    while True:
        try:
            step = int(progress_queue.get_nowait() or 0)
        except queue.Empty:
            break
        except Exception:
            break
        if step > 0:
            done += step
    return min(int(total), done)


def _push_progress(progress_queue, step):
    if progress_queue is None:
        return
    try:
        progress_queue.put_nowait(int(step))
    except Exception:
        return


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
        self.worst_sample = {
            'total_latency_ms': 0.0,
            'task_id': None,
            'chain_mode': 'core',
            'stage_timing_ms': {
                'standardize_ms': 0.0,
                'compress_ms': 0.0,
                'fuse_ms': 0.0,
            },
            'stage_share_pct': {
                'standardize_ms': 0.0,
                'compress_ms': 0.0,
                'fuse_ms': 0.0,
            },
            'dominant_stage': {
                'name': 'fuse_ms',
                'latency_ms': 0.0,
            },
        }
        self._worst_topk_limit = 5
        self.worst_topk: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @staticmethod
    def _make_worst_sample(latency_ms, stage_ms, task_id=None, chain_mode='core'):
        s_std = float((stage_ms or {}).get('standardize_ms', 0.0) or 0.0)
        s_cmp = float((stage_ms or {}).get('compress_ms', 0.0) or 0.0)
        s_fus = float((stage_ms or {}).get('fuse_ms', 0.0) or 0.0)
        total = max(float(latency_ms or 0.0), 1e-9)
        stage_map = {
            'standardize_ms': round4(s_std),
            'compress_ms': round4(s_cmp),
            'fuse_ms': round4(s_fus),
        }
        share = {
            'standardize_ms': round4((s_std / total) * 100.0),
            'compress_ms': round4((s_cmp / total) * 100.0),
            'fuse_ms': round4((s_fus / total) * 100.0),
        }
        dom_name, dom_val = max(stage_map.items(), key=lambda kv: float(kv[1] or 0.0))
        return {
            'total_latency_ms': round4(float(latency_ms or 0.0)),
            'task_id': task_id,
            'chain_mode': str(chain_mode or 'core'),
            'stage_timing_ms': stage_map,
            'stage_share_pct': share,
            'dominant_stage': {
                'name': dom_name,
                'latency_ms': round4(float(dom_val or 0.0)),
            },
        }

    def _update_worst_nolock(self, latency_ms, stage_ms, task_id=None, chain_mode='core'):
        lat = float(latency_ms or 0.0)
        sample = self._make_worst_sample(lat, stage_ms, task_id=task_id, chain_mode=chain_mode)
        self.worst_topk.append(sample)
        self.worst_topk.sort(key=lambda it: float(it.get('total_latency_ms', 0.0) or 0.0), reverse=True)
        if len(self.worst_topk) > self._worst_topk_limit:
            self.worst_topk = self.worst_topk[:self._worst_topk_limit]
        if lat > float(self.worst_sample.get('total_latency_ms', 0.0) or 0.0):
            self.worst_sample = sample

    def record_ok(self, latency_ms, stage_ms, task_id=None, chain_mode='core'):
        with self._lock:
            self.total += 1
            self.ok += 1
            self.latencies.append(latency_ms)
            for key in self.stage_latencies:
                self.stage_latencies[key].append(float(stage_ms.get(key, 0.0)))
            self._update_worst_nolock(latency_ms, stage_ms, task_id=task_id, chain_mode=chain_mode)

    def record_fail(self, exc):
        with self._lock:
            self.total += 1
            self.fail += 1
            self.errors.append(str(exc))

    def merge_chunk(self, latencies, stage_lists, errors, chain_mode='core'):
        """Merge a thread-local chunk in one lock section.

        Used by the optional batched collector to reduce hot lock contention.
        """
        ok_n = len(latencies)
        fail_n = len(errors)
        if ok_n == 0 and fail_n == 0:
            return
        with self._lock:
            self.total += ok_n + fail_n
            self.ok += ok_n
            self.fail += fail_n
            if ok_n > 0:
                self.latencies.extend(latencies)
                for key in self.stage_latencies:
                    self.stage_latencies[key].extend(stage_lists.get(key, []))
                top_n = min(self._worst_topk_limit, ok_n)
                top_idx = sorted(range(ok_n), key=lambda i: float(latencies[i] or 0.0), reverse=True)[:top_n]
                std_list = stage_lists.get('standardize_ms', []) or [0.0] * ok_n
                cmp_list = stage_lists.get('compress_ms', []) or [0.0] * ok_n
                fus_list = stage_lists.get('fuse_ms', []) or [0.0] * ok_n
                for i in top_idx:
                    stage_i = {
                        'standardize_ms': float(std_list[i]),
                        'compress_ms': float(cmp_list[i]),
                        'fuse_ms': float(fus_list[i]),
                    }
                    self._update_worst_nolock(latencies[i], stage_i, task_id=None, chain_mode=chain_mode)
            if fail_n > 0:
                self.errors.extend(errors)

    def summary(self) -> dict[str, Any]:
        stage_stats = {k: stats_from_values(v) for k, v in self.stage_latencies.items()}
        total_stats = stats_from_values(self.latencies)
        return {
            'total': self.total,
            'ok': self.ok,
            'fail': self.fail,
            'avg_latency_ms': total_stats['avg'],
            'p95_latency_ms': total_stats['p95'],
            'p99_latency_ms': total_stats['p99'],
            'p99_9_latency_ms': total_stats['p99_9'],
            'p99_99_latency_ms': total_stats['p99_99'],
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
            'worst_sample': dict(self.worst_sample),
            'worst_topk': list(self.worst_topk),
        }


def _pipeline_task(
    node,
    task_id,
    sensors,
    probe_header=False,
    parse_header_fn=None,
    chain_mode='core',
    e2e_send_fn=None,
):
    """Execute one stress iteration.

    core: standardize -> compress -> fuse
    e2e : standardize -> compress -> fuse -> dispatch -> receive/process
    """
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

        t_end = t3
        if chain_mode == 'e2e':
            sender = e2e_send_fn if callable(e2e_send_fn) else (lambda packet: bool(node.dispatch(packet, medium='UDP')))
            if not sender(pkt):
                raise ValueError('Loopback dispatch failed')
            t_end = time.perf_counter_ns()

        stage_ms = {
            'standardize_ms': (t1 - t0) / 1_000_000.0,
            'compress_ms': (t2 - t1) / 1_000_000.0,
            'fuse_ms': (t3 - t2) / 1_000_000.0,
        }
        latency_ms = (t_end - t_total_start) / 1_000_000.0
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
    return aggregate_run_series(series, suffix='_mean', include_variance=True, include_worst=True)


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
    chain_mode: str = 'core',
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
                    chain_mode=chain_mode,
                )
                samples.append(summary)

            aggregate = _aggregate_series(samples)
            representative = dict(samples[-1]) if samples else {}
            representative['throughput_pps'] = aggregate['throughput_pps_mean']
            representative['avg_latency_ms'] = aggregate['avg_latency_ms_mean']
            representative['p95_latency_ms'] = aggregate['p95_latency_ms_mean']
            representative['p99_latency_ms'] = aggregate['p99_latency_ms_mean']
            representative['p99_9_latency_ms'] = aggregate['p99_9_latency_ms_mean']
            representative['p99_99_latency_ms'] = aggregate['p99_99_latency_ms_mean']
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
                chain_mode=chain_mode,
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
        'chain_mode': str(chain_mode or 'core'),
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
               threads_per_process=None, progress_queue=None,
               progress_step=0, chain_mode='core') -> tuple['StressResult', dict[str, Any]]:
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
    chain_mode         : str        – core (pipeline only) or e2e (dispatch->receive loopback)

    Returns
    -------
    (StressResult, summary_dict)
    """
    preflight = _preflight(core_name=core_name)
    chain_mode = str(chain_mode or 'core').strip().lower()
    if chain_mode not in ('core', 'e2e'):
        raise RuntimeError('unknown chain_mode [{}], expected core/e2e'.format(chain_mode))
    process_count = max(1, int(processes or 1))
    per_process_threads = max(1, int(threads_per_process if threads_per_process is not None else workers))

    # Hybrid mode: split work across multiple processes, each running threaded stress.
    if process_count > 1:
        resolved_core_name = str(core_name or '').strip().lower() or None
        if not resolved_core_name:
            try:
                from opensynaptic.core import get_core_manager
                manager = get_core_manager()
                if config_path:
                    manager.set_config_path(config_path)
                resolved_core_name = str(manager.get_active_core_name() or '').strip().lower() or None
            except Exception:
                resolved_core_name = None
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
        completed_tasks = 0
        progress_lock = threading.Lock()

        def _render_progress():
            if not progress:
                return
            with progress_lock:
                print('\r' + _progress_line(completed_tasks, int(total), t_start), end='', flush=True)

        _ppool = ProcessPoolExecutor(max_workers=process_count, initializer=_init_worker_ignore_sigint)
        _progress_manager = None
        _progress_queue = None
        _interrupted = False
        _proc_futures: list[Any] = []
        try:
            if progress:
                import multiprocessing as _mp
                _progress_manager = _mp.Manager()
                _progress_queue = _progress_manager.Queue()
            for shard_total in shard_totals:
                kwargs = {
                    'total': int(shard_total),
                    'workers': int(per_process_threads),
                    'sources': int(sources),
                    'config_path': config_path,
                    'progress': False,
                    'core_name': resolved_core_name,
                    'expect_core': expect_core,
                    'expect_codec_class': expect_codec_class,
                    'header_probe_rate': header_probe_rate,
                    'batch_size': batch_size,
                    'processes': 1,
                    'threads_per_process': None,
                    'progress_queue': _progress_queue,
                    'progress_step': max(1024, int(batch_size or 1) * 4),
                    'chain_mode': chain_mode,
                }
                _proc_futures.append(_ppool.submit(_process_worker_run_stress, kwargs))

            pending = set(_proc_futures)
            while pending:
                done, pending = wait(pending, timeout=0.10, return_when=FIRST_COMPLETED)
                if _progress_queue is not None:
                    completed_tasks = _drain_progress_queue(_progress_queue, completed_tasks, int(total))
                if done:
                    for fut in done:
                        child_summaries.append(fut.result())
                _render_progress()

            if _progress_queue is not None:
                completed_tasks = _drain_progress_queue(_progress_queue, completed_tasks, int(total))
                _render_progress()
            # Normal completion – clean shutdown (wait for internal resources).
            _ppool.shutdown(wait=True)
        except KeyboardInterrupt:
            _interrupted = True
            print('\n[stress] Ctrl+C – cancelling child processes…', file=sys.stderr, flush=True)
            for f in _proc_futures:
                f.cancel()
            # KI path – don't block; let OS reclaim resources.
            _ppool.shutdown(wait=False, cancel_futures=True)
        finally:
            if _progress_manager is not None:
                try:
                    _progress_manager.shutdown()
                except Exception:
                    pass

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

    def _build_e2e_sender(attached_node):
        receive_fn = getattr(attached_node, 'receive', None)
        fusion = getattr(attached_node, 'fusion', None)
        decompress_fn = getattr(fusion, 'decompress', None)
        dispatch_fn = getattr(attached_node, 'dispatch', None)

        def _send(packet):
            try:
                if callable(receive_fn):
                    decoded = receive_fn(packet)
                    return not (isinstance(decoded, dict) and decoded.get('error'))
                if callable(decompress_fn):
                    decoded = decompress_fn(packet)
                    return not (isinstance(decoded, dict) and decoded.get('error'))
                if callable(dispatch_fn):
                    return bool(dispatch_fn(packet, medium='UDP'))
                return False
            except Exception:
                return False

        return _send

    e2e_fast_sender = _build_e2e_sender(node) if chain_mode == 'e2e' else None
    _thread_node_tls = threading.local()
    # Pre-build sensor sets
    sensor_sets = []
    for i in range(sources):
        sensor_sets.append([
            [f'V{i}', 'OK', float(100 + i * 3), 'Pa'],
            [f'T{i}', 'OK', float(20 + i), 'Cel'],
        ])

    result = StressResult()
    runtime_opts = _resolve_stress_runtime_options(node=node, config_path=config_path)
    collector_mode = str(runtime_opts.get('collector_mode', 'legacy'))
    collector_flush_every = max(1, int(runtime_opts.get('collector_flush_every', 256) or 256))
    collector_flush_explicit = bool(runtime_opts.get('collector_flush_explicit', False))
    pipeline_mode = str(runtime_opts.get('pipeline_mode', 'legacy'))
    gc_mode = str(runtime_opts.get('gc_mode', 'auto') or 'auto').strip().lower()
    flush_auto_tuned = False
    if chain_mode == 'e2e':
        # e2e mode must execute dispatch/receive processing per item; fused shortcut skips that path.
        pipeline_mode = 'legacy'
        if collector_mode == 'batched' and not collector_flush_explicit and int(total) >= 500_000 and collector_flush_every < 1024:
            collector_flush_every = 1024
            flush_auto_tuned = True

    gc_was_enabled = gc.isenabled()
    disable_gc = (gc_mode == 'off') or (gc_mode == 'auto' and chain_mode == 'e2e')
    if disable_gc and gc_was_enabled:
        gc.disable()

    # ── Optional batch pipeline setup ─────────────────────────────────────
    _pipeline_batch = None
    _pipeline_batch_tls = threading.local()
    _pipeline_batch_compressor = None
    _pipeline_fusion_factory = None
    pre_packed_facts: list[bytes] = []
    if pipeline_mode == 'batch_fused':
        try:
            from opensynaptic.core.rscore.codec import RsPipelineBatch, has_pipeline_batch
            if pipeline_mode == 'batch_fused' and has_pipeline_batch():
                _compressor = getattr(getattr(node, 'engine', None), '_rs_solidity', None)
                _fusion_ffi = getattr(getattr(node, 'fusion', None), '_ffi', None)
                if _compressor is not None and _fusion_ffi is not None:
                    _pipeline_batch_compressor = _compressor
                    try:
                        from opensynaptic.core.rscore.codec import RsOSVisualFusionEngine
                        _pipeline_fusion_factory = RsOSVisualFusionEngine
                        _pipeline_batch = RsPipelineBatch(_compressor, _pipeline_fusion_factory())
                    except Exception:
                        _pipeline_fusion_factory = None
                        _pipeline_batch = RsPipelineBatch(_compressor, _fusion_ffi)
                    if not _pipeline_batch.available:
                        _pipeline_batch = None
            # Pre-pack facts for each sensor set (bypass Rust stub standardizer)
            # Build proper fact dicts directly – matches pycore standardize output shape
            if sensor_sets:
                for i, s_set in enumerate(sensor_sets):
                    fact: dict[str, Any] = {
                        'id': f'STRESS_{i % 8}',
                        's': 'ONLINE',
                        't': 0.0,
                    }
                    for j, s_data in enumerate(s_set, start=1):
                        s_id, s_st, s_val, s_unit = s_data
                        fact[f's{j}_id'] = str(s_id)
                        fact[f's{j}_s'] = str(s_st)
                        fact[f's{j}_v'] = float(s_val)
                        fact[f's{j}_u'] = str(s_unit)
                    pre_packed_facts.append(RsPipelineBatch.pack_fact(fact))
        except Exception:
            _pipeline_batch = None
            pre_packed_facts = []
            pipeline_mode = 'legacy'
    completed = [0]
    progress_lock = threading.Lock()
    probe_lock = threading.Lock()
    progress_state = {'last_print_at': 0.0}
    progress_emit_step = max(1, int(progress_step or 1))
    progress_emit_pending = [0]

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
    # Pre-compute fixed assigned_id used in all pipeline calls
    _aid = int(getattr(node, 'assigned_id', 42) or 42)
    legacy_mode = (collector_mode == 'legacy')

    def _commit_progress(step_count):
        if progress_queue is not None:
            if progress_emit_step <= 1:
                _push_progress(progress_queue, step_count)
            else:
                with progress_lock:
                    progress_emit_pending[0] += int(step_count)
                    if progress_emit_pending[0] >= progress_emit_step:
                        _push_progress(progress_queue, progress_emit_pending[0])
                        progress_emit_pending[0] = 0
        if not progress:
            return
        with progress_lock:
            completed[0] += step_count
            now = time.monotonic()
            if (completed[0] >= total) or (now - progress_state['last_print_at'] >= 0.10):
                print('\r' + _progress_line(completed[0], total, t_start), end='', flush=True)
                progress_state['last_print_at'] = now

    def _task_range(start_idx, end_idx):
        range_count = end_idx - start_idx

        # ── batch_fused: one Rust call for the entire range ────────────────
        if pipeline_mode == 'batch_fused' and _pipeline_batch is not None and pre_packed_facts:
            local_batch = getattr(_pipeline_batch_tls, 'batch', None)
            if local_batch is None:
                local_batch = _pipeline_batch
                if _pipeline_batch_compressor is not None and callable(_pipeline_fusion_factory):
                    try:
                        candidate = RsPipelineBatch(_pipeline_batch_compressor, _pipeline_fusion_factory())
                        if candidate.available:
                            local_batch = candidate
                    except Exception:
                        local_batch = _pipeline_batch
                _pipeline_batch_tls.batch = local_batch
            batch_items = [
                (pre_packed_facts[idx % sources], _aid, True)
                for idx in range(start_idx, end_idx)
            ]
            t_b0 = time.perf_counter_ns()
            packets = local_batch.run_batch(batch_items)
            t_b1 = time.perf_counter_ns()
            avg_ms = ((t_b1 - t_b0) / max(1, range_count)) / 1_000_000.0
            stage_avg = avg_ms / 3.0
            b_latencies, b_stage, b_errors = [], {'standardize_ms': [], 'compress_ms': [], 'fuse_ms': []}, []
            for pkt in packets:
                if not pkt:
                    b_errors.append('batch_pipeline_item_failed')
                else:
                    b_latencies.append(avg_ms)
                    b_stage['standardize_ms'].append(stage_avg)
                    b_stage['compress_ms'].append(stage_avg)
                    b_stage['fuse_ms'].append(stage_avg)
            result.merge_chunk(b_latencies, b_stage, b_errors, chain_mode=chain_mode)
            _commit_progress(range_count)
            return

        # ── legacy / batched: per-item pipeline task ──────────────────────
        local_latencies = []
        local_stage = {'standardize_ms': [], 'compress_ms': [], 'fuse_ms': []}
        local_errors = []
        local_probe = {'attempted': 0, 'parsed': 0, 'crc16_ok': 0}

        def _flush_local():
            if legacy_mode:
                return
            result.merge_chunk(local_latencies, local_stage, local_errors, chain_mode=chain_mode)
            if local_probe['attempted'] > 0:
                with probe_lock:
                    header_probe_stats['attempted'] += local_probe['attempted']
                    header_probe_stats['parsed'] += local_probe['parsed']
                    header_probe_stats['crc16_ok'] += local_probe['crc16_ok']
            local_latencies.clear()
            local_errors.clear()
            for key in local_stage:
                local_stage[key].clear()
            local_probe['attempted'] = 0
            local_probe['parsed'] = 0
            local_probe['crc16_ok'] = 0

        for idx in range(start_idx, end_idx):
            active_node = node
            active_sender = e2e_fast_sender
            if chain_mode == 'e2e':
                worker_ctx = getattr(_thread_node_tls, 'ctx', None)
                if worker_ctx is None:
                    local_node = _make_node(config_path, core_name=core_name)
                    worker_ctx = (local_node, _build_e2e_sender(local_node))
                    _thread_node_tls.ctx = worker_ctx
                active_node, active_sender = worker_ctx

            sensors = sensor_sets[idx % sources]
            do_probe = bool(probe_every > 0 and (idx % probe_every == 0) and callable(parse_header_fn))
            latency, stage_ms, exc, header_probe = _pipeline_task(
                active_node, idx, sensors, probe_header=do_probe, parse_header_fn=parse_header_fn,
                chain_mode=chain_mode,
                e2e_send_fn=active_sender,
            )

            if legacy_mode:
                if exc is not None:
                    result.record_fail(exc)
                else:
                    result.record_ok(latency, stage_ms, task_id=idx, chain_mode=chain_mode)
                    if header_probe and header_probe.get('attempted'):
                        with probe_lock:
                            header_probe_stats['attempted'] += 1
                            if header_probe.get('parsed'):
                                header_probe_stats['parsed'] += 1
                            if header_probe.get('crc16_ok'):
                                header_probe_stats['crc16_ok'] += 1
            else:
                if exc is not None:
                    local_errors.append(str(exc))
                else:
                    local_latencies.append(float(latency or 0.0))
                    local_stage['standardize_ms'].append(float(stage_ms.get('standardize_ms', 0.0)))
                    local_stage['compress_ms'].append(float(stage_ms.get('compress_ms', 0.0)))
                    local_stage['fuse_ms'].append(float(stage_ms.get('fuse_ms', 0.0)))
                    if header_probe and header_probe.get('attempted'):
                        local_probe['attempted'] += 1
                        if header_probe.get('parsed'):
                            local_probe['parsed'] += 1
                        if header_probe.get('crc16_ok'):
                            local_probe['crc16_ok'] += 1
                if (idx - start_idx + 1) % collector_flush_every == 0:
                    _flush_local()

        _flush_local()
        _commit_progress(range_count)

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

    if progress_queue is not None and progress_emit_pending[0] > 0:
        _push_progress(progress_queue, progress_emit_pending[0])
        progress_emit_pending[0] = 0

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
    summary['chain_mode'] = chain_mode
    summary['runtime_toggles'] = {
        'collector_mode': collector_mode,
        'collector_flush_every': collector_flush_every,
        'collector_flush_auto_tuned': bool(flush_auto_tuned),
        'pipeline_mode': pipeline_mode,
        'pipeline_batch_available': _pipeline_batch is not None and getattr(_pipeline_batch, 'available', False),
        'gc_mode': gc_mode,
        'gc_disabled_during_run': bool(disable_gc),
        'chain_mode': chain_mode,
    }
    ws = summary.get('worst_sample') if isinstance(summary.get('worst_sample'), dict) else None
    if ws:
        ws['chain_mode'] = chain_mode
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

    if disable_gc and gc_was_enabled:
        gc.enable()
    return result, summary


if __name__ == '__main__':
    res, summary = run_stress(total=200, workers=8, sources=6)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    sys.exit(0 if res.fail == 0 else 1)

