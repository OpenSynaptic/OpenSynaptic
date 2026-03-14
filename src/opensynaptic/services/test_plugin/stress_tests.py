"""
stress_tests.py – Concurrent transmit / pipeline stress tests for OpenSynaptic.

Run via:
    python -u src/main.py plugin-test --suite stress --workers 8 --total 200
"""
import sys
import time
import threading
import traceback
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


def _make_node(config_path=None):
    from opensynaptic.core.core import OpenSynaptic
    return OpenSynaptic(config_path)


class StressResult:
    """Aggregated result from a stress run."""

    def __init__(self):
        self.total = 0
        self.ok = 0
        self.fail = 0
        self.errors = []
        self.latencies = []
        self._lock = threading.Lock()

    def record_ok(self, latency_ms):
        with self._lock:
            self.total += 1
            self.ok += 1
            self.latencies.append(latency_ms)

    def record_fail(self, exc):
        with self._lock:
            self.total += 1
            self.fail += 1
            self.errors.append(str(exc))

    def summary(self):
        avg = sum(self.latencies) / len(self.latencies) if self.latencies else 0.0
        p95 = sorted(self.latencies)[int(len(self.latencies) * 0.95)] if self.latencies else 0.0
        return {
            'total': self.total,
            'ok': self.ok,
            'fail': self.fail,
            'avg_latency_ms': round(avg, 2),
            'p95_latency_ms': round(p95, 2),
            'error_samples': self.errors[:5],
        }


def _pipeline_task(node, task_id, sensors):
    """Execute one full pipeline (standardize → compress → fuse) without dispatch."""
    t0 = time.monotonic()
    try:
        device_id = f'STRESS_{task_id % 8}'
        fact = node.standardizer.standardize(device_id, 'ONLINE', sensors)
        compressed = node.engine.compress(fact)
        aid = getattr(node, 'assigned_id', 42) or 42
        raw_input = f'{aid};{compressed}'
        pkt = node.fusion.run_engine(raw_input, strategy='FULL')
        if not pkt or len(pkt) == 0:
            raise ValueError('Empty packet produced')
        latency_ms = (time.monotonic() - t0) * 1000
        return latency_ms, None
    except Exception as exc:
        return None, exc


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
    lock = threading.Lock()

    def _task(idx):
        sensors = sensor_sets[idx % sources]
        latency, exc = _pipeline_task(node, idx, sensors)
        if exc is not None:
            result.record_fail(exc)
        else:
            result.record_ok(latency)
        if progress:
            with lock:
                completed[0] += 1
                if completed[0] % max(1, total // 10) == 0:
                    pct = completed[0] * 100 // total
                    print(f'\r  Progress: {completed[0]}/{total} ({pct}%)', end='', flush=True)

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
    import json
    res, summary = run_stress(total=200, workers=8, sources=6)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    sys.exit(0 if res.fail == 0 else 1)

