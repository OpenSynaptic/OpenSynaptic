#!/usr/bin/env python
"""Phase-2 performance playbook runner for OpenSynaptic stress tuning.

This script automates the second five optimization steps:
6) Stability regression on the phase-1 best candidate.
7) Core vs e2e overhead split on the same shape.
8) Concurrency neighborhood re-check around the winner.
9) collector_flush_every sensitivity sweep (isolated config copies).
10) Gate evaluation + recommendation output.

It only drives existing CLI commands and writes JSON artifacts.
"""

from __future__ import annotations

import argparse
import copy
import glob
import json
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunSpec:
    name: str
    processes: int
    threads_per_process: int
    batch_size: int


def _now_tag() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _safe_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _safe_int(v: Any) -> int:
    try:
        return int(v)
    except Exception:
        return 0


def _latest_phase1_summary(repo_root: Path) -> Path:
    files = sorted(glob.glob(str(repo_root / "data/benchmarks/phase1/phase1_summary_*.json")))
    if not files:
        raise RuntimeError("phase1 summary not found; run scripts/phase1_perf_playbook.py first")
    return Path(files[-1])


def _run_stress(
    repo_root: Path,
    config_path: str | None,
    total: int,
    spec: RunSpec,
    chain_mode: str,
    out_file: Path,
) -> dict[str, Any]:
    cmd = [
        sys.executable,
        "-u",
        "src/main.py",
        "plugin-test",
        "--suite",
        "stress",
        "--total",
        str(total),
        "--processes",
        str(spec.processes),
        "--threads-per-process",
        str(spec.threads_per_process),
        "--batch-size",
        str(spec.batch_size),
        "--chain-mode",
        chain_mode,
        "--no-progress",
        "--json-out",
        str(out_file),
    ]
    if config_path:
        cmd[4:4] = ["--config", config_path]

    completed = subprocess.run(cmd, cwd=str(repo_root), check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"stress run failed: {spec.name} ({chain_mode}), rc={completed.returncode}")

    return json.loads(out_file.read_text(encoding="utf-8"))


def _extract_bottleneck(summary: dict[str, Any]) -> dict[str, Any]:
    ws = summary.get("worst_sample") if isinstance(summary.get("worst_sample"), dict) else {}
    st = ws.get("stage_timing_ms") if isinstance(ws.get("stage_timing_ms"), dict) else {}
    total = _safe_float(ws.get("total_latency_ms"))
    tracked = _safe_float(st.get("standardize_ms")) + _safe_float(st.get("compress_ms")) + _safe_float(st.get("fuse_ms"))
    untracked = max(0.0, total - tracked)
    return {
        "worst_total_latency_ms": round(total, 4),
        "worst_tracked_stage_sum_ms": round(tracked, 4),
        "worst_untracked_latency_ms": round(untracked, 4),
        "worst_untracked_ratio_pct": round((untracked / total) * 100.0, 4) if total > 0 else 0.0,
        "worst_dominant_stage": ((ws.get("dominant_stage") or {}).get("name") if isinstance(ws, dict) else None),
    }


def _row(spec: RunSpec, chain_mode: str, summary: dict[str, Any], out_file: Path, repeat: int | None = None, label: str | None = None) -> dict[str, Any]:
    row = {
        "spec": spec.name,
        "label": label or spec.name,
        "chain_mode": chain_mode,
        "processes": spec.processes,
        "threads_per_process": spec.threads_per_process,
        "batch_size": spec.batch_size,
        "throughput_pps": _safe_float(summary.get("throughput_pps")),
        "p99_99_latency_ms": _safe_float(summary.get("p99_99_latency_ms")),
        "max_latency_ms": _safe_float(summary.get("max_latency_ms")),
        "fail": _safe_int(summary.get("fail", 0)),
        "bottleneck": _extract_bottleneck(summary),
        "file": str(out_file),
    }
    if repeat is not None:
        row["repeat"] = int(repeat)
    return row


def _make_flush_config(repo_root: Path, base_config_path: str | None, flush_value: int, out_dir: Path) -> Path:
    cfg_path = Path(base_config_path) if base_config_path else (repo_root / "Config.json")
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg = copy.deepcopy(data)
    stress_rt = (
        cfg.setdefault("RESOURCES", {})
        .setdefault("service_plugins", {})
        .setdefault("test_plugin", {})
        .setdefault("stress_runtime", {})
    )
    stress_rt["collector_flush_every"] = int(flush_value)

    out_file = out_dir / f"Config_phase2_flush{int(flush_value)}.json"
    out_file.write_text(json.dumps(cfg, ensure_ascii=False, indent=4), encoding="utf-8")
    return out_file


def _gate_eval(rows: list[dict[str, Any]], baseline_pps: float, baseline_p99_99: float) -> dict[str, Any]:
    if not rows:
        return {"pass": False, "reason": "no rows"}

    all_fail_zero = all(_safe_int(r.get("fail", 1)) == 0 for r in rows)
    best_pps = max(_safe_float(r.get("throughput_pps")) for r in rows)
    best_tail = min(_safe_float(r.get("p99_99_latency_ms")) for r in rows)

    # conservative gate: keep throughput >= 95% baseline and tail <= 120% baseline
    pps_gate = best_pps >= (baseline_pps * 0.95)
    tail_gate = best_tail <= (baseline_p99_99 * 1.20)

    return {
        "pass": bool(all_fail_zero and pps_gate and tail_gate),
        "all_fail_zero": all_fail_zero,
        "pps_gate": pps_gate,
        "tail_gate": tail_gate,
        "baseline": {
            "throughput_pps": round(baseline_pps, 4),
            "p99_99_latency_ms": round(baseline_p99_99, 4),
        },
        "best_seen": {
            "throughput_pps": round(best_pps, 4),
            "p99_99_latency_ms": round(best_tail, 4),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run phase-2 perf playbook (second five steps).")
    parser.add_argument("--repo-root", default=".", help="OpenSynaptic repository root")
    parser.add_argument("--phase1-summary", default=None, help="Path to phase1_summary_*.json")
    parser.add_argument("--config", default=None, help="Optional base Config.json path")
    parser.add_argument("--total", type=int, default=300000, help="Stress total iterations for phase-2")
    parser.add_argument("--repeats", type=int, default=3, help="Stability repeat count")
    parser.add_argument("--out-dir", default="data/benchmarks/phase2", help="Output directory")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    out_dir = (repo_root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = _now_tag()

    phase1_summary_path = Path(args.phase1_summary).resolve() if args.phase1_summary else _latest_phase1_summary(repo_root)
    phase1 = json.loads(phase1_summary_path.read_text(encoding="utf-8"))

    best1 = phase1.get("best_batch_candidate") or phase1.get("best_concurrency_candidate") or {}
    best_spec = RunSpec(
        name=str(best1.get("spec", "phase1_best")),
        processes=_safe_int(best1.get("processes", 12)),
        threads_per_process=_safe_int(best1.get("threads_per_process", 2)),
        batch_size=_safe_int(best1.get("batch_size", 256)),
    )
    baseline_pps = _safe_float(phase1.get("throughput_stats", {}).get("baseline_max", 0.0))
    baseline_p99_99 = _safe_float(best1.get("p99_99_latency_ms", 0.0)) or 1.0

    # Step 6: stability regression on winner (e2e)
    stability_rows: list[dict[str, Any]] = []
    for i in range(args.repeats):
        out_file = out_dir / f"stability_{best_spec.name}_r{i+1}_{tag}.json"
        summary = _run_stress(repo_root, args.config, args.total, best_spec, "e2e", out_file)
        stability_rows.append(_row(best_spec, "e2e", summary, out_file, repeat=i + 1, label="stability"))

    # Step 7: core vs e2e split on same shape
    split_rows: list[dict[str, Any]] = []
    for mode in ("core", "e2e"):
        out_file = out_dir / f"split_{best_spec.name}_{mode}_{tag}.json"
        summary = _run_stress(repo_root, args.config, args.total, best_spec, mode, out_file)
        split_rows.append(_row(best_spec, mode, summary, out_file, label="chain_split"))

    # Step 8: concurrency neighborhood around winner (keep total threads near constant)
    total_threads = max(1, best_spec.processes * best_spec.threads_per_process)
    neighbor_specs = [
        RunSpec(f"p{best_spec.processes}_t{best_spec.threads_per_process}_b{best_spec.batch_size}", best_spec.processes, best_spec.threads_per_process, best_spec.batch_size),
        RunSpec(f"p{max(1, best_spec.processes//2)}_t{max(1, total_threads // max(1, best_spec.processes//2))}_b{best_spec.batch_size}", max(1, best_spec.processes // 2), max(1, total_threads // max(1, best_spec.processes // 2)), best_spec.batch_size),
        RunSpec(f"p{min(total_threads, best_spec.processes*2)}_t{max(1, total_threads // min(total_threads, best_spec.processes*2))}_b{best_spec.batch_size}", min(total_threads, best_spec.processes * 2), max(1, total_threads // min(total_threads, best_spec.processes * 2)), best_spec.batch_size),
    ]
    seen = set()
    uniq_neighbor_specs: list[RunSpec] = []
    for s in neighbor_specs:
        key = (s.processes, s.threads_per_process, s.batch_size)
        if key in seen:
            continue
        seen.add(key)
        uniq_neighbor_specs.append(s)

    neighbor_rows: list[dict[str, Any]] = []
    for spec in uniq_neighbor_specs:
        out_file = out_dir / f"neighbor_{spec.name}_{tag}.json"
        summary = _run_stress(repo_root, args.config, args.total, spec, "e2e", out_file)
        neighbor_rows.append(_row(spec, "e2e", summary, out_file, label="neighbor"))

    # Step 9: flush sensitivity sweep via isolated config copy
    flush_rows: list[dict[str, Any]] = []
    for flush in (256, 512, 1024):
        cfg_file = _make_flush_config(repo_root, args.config, flush, out_dir)
        out_file = out_dir / f"flush{flush}_{best_spec.name}_{tag}.json"
        summary = _run_stress(repo_root, str(cfg_file), args.total, best_spec, "e2e", out_file)
        row = _row(best_spec, "e2e", summary, out_file, label=f"flush_{flush}")
        row["collector_flush_every"] = int(flush)
        row["config_file"] = str(cfg_file)
        flush_rows.append(row)

    # Step 10: gate + recommendation
    all_rows = stability_rows + split_rows + neighbor_rows + flush_rows
    gate = _gate_eval(all_rows, baseline_pps=baseline_pps, baseline_p99_99=baseline_p99_99)

    # recommendation: choose best e2e row by throughput then tail
    e2e_rows = [r for r in all_rows if str(r.get("chain_mode")) == "e2e"]
    best_e2e = sorted(
        e2e_rows,
        key=lambda r: (_safe_float(r.get("throughput_pps")), -_safe_float(r.get("p99_99_latency_ms"))),
        reverse=True,
    )[0] if e2e_rows else None

    summary_doc = {
        "phase2_generated_at": tag,
        "phase1_summary": str(phase1_summary_path),
        "target": phase1.get("target", {}),
        "baseline_reference": {
            "throughput_pps": baseline_pps,
            "p99_99_latency_ms": baseline_p99_99,
            "best_phase1": best1,
        },
        "step6_stability": stability_rows,
        "step7_chain_split": split_rows,
        "step8_concurrency_neighbors": neighbor_rows,
        "step9_flush_sweep": flush_rows,
        "step10_gate": gate,
        "recommended": best_e2e,
        "recommended_command": (
            "python -u src/main.py plugin-test --suite stress "
            f"--total {args.total} --processes {best_e2e['processes']} "
            f"--threads-per-process {best_e2e['threads_per_process']} "
            f"--batch-size {best_e2e['batch_size']} --chain-mode e2e --no-progress"
        ) if best_e2e else None,
    }

    out_summary = out_dir / f"phase2_summary_{tag}.json"
    out_summary.write_text(json.dumps(summary_doc, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(
        {
            "ok": True,
            "summary": str(out_summary),
            "gate_pass": bool(gate.get("pass", False)),
            "recommended_spec": best_e2e.get("spec") if best_e2e else None,
        },
        ensure_ascii=False,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

