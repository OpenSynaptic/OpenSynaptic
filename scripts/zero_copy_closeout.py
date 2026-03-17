"""
Zero-copy closeout harness for OpenSynaptic.

Runs:
1) component suite once (compatibility gate)
2) single-core stress suite N times (workers=1)
3) reports median PPS + stage timings

Usage:
    py -3 -u scripts/zero_copy_closeout.py
    py -3 -u scripts/zero_copy_closeout.py --runs 3 --total 100000 --config Config.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path


def _run_component(root: Path) -> tuple[bool, str]:
    cmd = [sys.executable, "-u", "src/main.py", "plugin-test", "--suite", "component"]
    proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    return (proc.returncode == 0), output


def _run_single_stress(root: Path, total: int, config_path: str) -> dict:
    code = f"""
import json, sys
from pathlib import Path
root = Path(r'''{str(root)}''')
sys.path.insert(0, str(root / 'src'))
sys.path.insert(0, str(root))
from opensynaptic.services.test_plugin.stress_tests import run_stress
_, s = run_stress(total={int(total)}, workers=1, sources=6, config_path=r'''{config_path}''', progress=False)
print(json.dumps(s, ensure_ascii=False))
"""
    proc = subprocess.run([sys.executable, "-u", "-c", code], cwd=str(root), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stdout or "") + "\n" + (proc.stderr or ""))
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    # Last JSON line is summary
    summary = json.loads(lines[-1])
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="OpenSynaptic zero-copy closeout harness")
    parser.add_argument("--runs", type=int, default=3, help="single-core stress runs")
    parser.add_argument("--total", type=int, default=100000, help="stress iterations per run")
    parser.add_argument("--config", default="Config.json", help="config path (absolute or workspace-relative)")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    cfg = Path(args.config)
    if not cfg.is_absolute():
        cfg = (root / cfg).resolve()

    ok, comp_output = _run_component(root)
    print("=== component suite ===")
    print("PASS" if ok else "FAIL")
    if not ok:
        print(comp_output)
        return 1

    print("=== single-core stress ===")
    rows = []
    for i in range(max(1, args.runs)):
        s = _run_single_stress(root, total=max(1, args.total), config_path=str(cfg))
        row = {
            "run": i + 1,
            "pps": float(s.get("throughput_pps", 0.0)),
            "avg_ms": float(s.get("avg_latency_ms", 0.0)),
            "p95_ms": float(s.get("p95_latency_ms", 0.0)),
            "fuse_avg_ms": float(((s.get("stage_timing_ms", {}) or {}).get("fuse_ms", {}) or {}).get("avg", 0.0)),
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False))

    pps_vals = [r["pps"] for r in rows]
    summary = {
        "runs": len(rows),
        "total_per_run": int(args.total),
        "single_core_pps_median": round(statistics.median(pps_vals), 2),
        "single_core_pps_min": round(min(pps_vals), 2),
        "single_core_pps_max": round(max(pps_vals), 2),
    }
    print("=== closeout summary ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

