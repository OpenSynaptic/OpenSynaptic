"""
stress_tests.py – Concurrent transmit / pipeline stress tests for OpenSynaptic.

Run via:
    python -u src/main.py plugin-test --suite stress --workers 8 --total 200
"""
import json
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

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


def _make_node(config_path=None):
    from opensynaptic.core import OpenSynaptic
    return OpenSynaptic(config_path)


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

    def summary(self):
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
        }


def _pipeline_task(node, task_id, sensors):
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
        stage_ms = {
            'standardize_ms': (t1 - t0) / 1_000_000.0,
            'compress_ms': (t2 - t1) / 1_000_000.0,
            'fuse_ms': (t3 - t2) / 1_000_000.0,
        }
        latency_ms = (t3 - t_total_start) / 1_000_000.0
        return latency_ms, stage_ms, None
    except Exception as exc:
        return None, None, exc


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


def run_stress(total=200, workers=8, sources=6, config_path=None, progress=True):
    """
    Run a concurrent pipeline stress test.

    Parameters
    ----------
    total : int   – total number of encode cycles
    workers : int – thread pool size
    sources : int – number of distinct sensor configurations (rotated round-robin)
    config_path : str | None – path to Config.json; None uses ctx auto-detection

    Returns
    -------
    StressResult
    """
    if not has_native_library('os_base62') or not has_native_library('os_security'):
        raise RuntimeError('Stress suite requires os_base62 and os_security native libraries')
    node = _make_node(config_path)
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

    def _task(idx):
        sensors = sensor_sets[idx % sources]
        latency, stage_ms, exc = _pipeline_task(node, idx, sensors)
        if exc is not None:
            result.record_fail(exc)
        else:
            result.record_ok(latency, stage_ms)
        if progress:
            with progress_lock:
                completed[0] += 1
                now = time.monotonic()
                should_print = (completed[0] >= total) or (now - progress_state['last_print_at'] >= 0.10)
                if should_print:
                    print('\r' + _progress_line(completed[0], total, t_start), end='', flush=True)
                    progress_state['last_print_at'] = now

    t_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_task, i) for i in range(total)]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception:
                pass
    elapsed = time.monotonic() - t_start
    if progress:
        print()  # newline after progress

    summary = result.summary()
    summary['elapsed_s'] = round(elapsed, 3)
    summary['throughput_pps'] = round(total / elapsed, 1) if elapsed > 0 else 0.0
    return result, summary


if __name__ == '__main__':
    res, summary = run_stress(total=200, workers=8, sources=6)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    sys.exit(0 if res.fail == 0 else 1)

