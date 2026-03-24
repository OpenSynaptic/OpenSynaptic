#!/usr/bin/env python
"""Phase-1 performance playbook runner for OpenSynaptic e2e stress.

This script automates the first five optimization steps:
1) Freeze target/spec metadata.
2) Baseline matrix runs.
3) Bottleneck extraction from worst_sample/worst_topk.
4) Concurrency shape search.
5) Batch-size neighborhood search.

It only drives existing CLI commands and never changes runtime logic.
"""

from __future__ import annotations

import argparse
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


def _run_stress(repo_root: Path, config_path: str | None, total: int, spec: RunSpec, chain_mode: str, out_file: Path) -> dict[str, Any]:
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
        raise RuntimeError(f"stress run failed: {spec.name}, rc={completed.returncode}")

    return json.loads(out_file.read_text(encoding="utf-8"))


def _safe_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _extract_bottleneck(summary: dict[str, Any]) -> dict[str, Any]:
    ws = summary.get("worst_sample") if isinstance(summary.get("worst_sample"), dict) else {}
    st = ws.get("stage_timing_ms") if isinstance(ws.get("stage_timing_ms"), dict) else {}
    s_std = _safe_float(st.get("standardize_ms"))
    s_cmp = _safe_float(st.get("compress_ms"))
    s_fus = _safe_float(st.get("fuse_ms"))
    total = _safe_float(ws.get("total_latency_ms"))
    tracked = s_std + s_cmp + s_fus
    untracked = max(0.0, total - tracked)

    topk = summary.get("worst_topk") if isinstance(summary.get("worst_topk"), list) else []
    dom_count: dict[str, int] = {}
    for item in topk:
        if not isinstance(item, dict):
            continue
        dom = item.get("dominant_stage") if isinstance(item.get("dominant_stage"), dict) else {}
        name = str(dom.get("name", "unknown"))
        dom_count[name] = dom_count.get(name, 0) + 1

    return {
        "worst_total_latency_ms": round(total, 4),
        "worst_tracked_stage_sum_ms": round(tracked, 4),
        "worst_untracked_latency_ms": round(untracked, 4),
        "worst_untracked_ratio_pct": round((untracked / total) * 100.0, 4) if total > 0 else 0.0,
        "worst_dominant_stage": (ws.get("dominant_stage") or {}).get("name"),
        "worst_topk_dominant_stage_counts": dom_count,
    }


def _choose_best_by_throughput(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise RuntimeError("no benchmark rows")
    rows_sorted = sorted(rows, key=lambda r: (_safe_float(r.get("throughput_pps")), -_safe_float(r.get("p99_99_latency_ms"))), reverse=True)
    return rows_sorted[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run phase-1 perf playbook (first five steps).")
    parser.add_argument("--repo-root", default=".", help="OpenSynaptic repository root")
    parser.add_argument("--config", default=None, help="Optional Config.json path")
    parser.add_argument("--total", type=int, default=1000000, help="Stress total iterations")
    parser.add_argument("--chain-mode", choices=["core", "e2e"], default="e2e")
    parser.add_argument("--repeats", type=int, default=1, help="Repeat count per spec")
    parser.add_argument("--out-dir", default="data/benchmarks/phase1", help="Output directory")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    out_dir = (repo_root / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = _now_tag()

    # Step 1: freeze target/spec metadata
    target = {
        "target_throughput_pps": 1_000_000,
        "suite": "stress",
        "chain_mode": args.chain_mode,
        "total": int(args.total),
        "repeats": int(args.repeats),
        "generated_at": tag,
    }
    (out_dir / f"target_{tag}.json").write_text(json.dumps(target, indent=2, ensure_ascii=False), encoding="utf-8")

    # Step 2+4 baseline/concurrency matrix
    baseline_specs = [
        RunSpec("p12_t2_b256", 12, 2, 256),
        RunSpec("p6_t4_b256", 6, 4, 256),
        RunSpec("p4_t6_b256", 4, 6, 256),
    ]

    rows: list[dict[str, Any]] = []
    for spec in baseline_specs:
        for i in range(args.repeats):
            out_file = out_dir / f"{spec.name}_r{i+1}_{tag}.json"
            summary = _run_stress(repo_root, args.config, args.total, spec, args.chain_mode, out_file)
            row = {
                "spec": spec.name,
                "processes": spec.processes,
                "threads_per_process": spec.threads_per_process,
                "batch_size": spec.batch_size,
                "repeat": i + 1,
                "throughput_pps": _safe_float(summary.get("throughput_pps")),
                "p99_99_latency_ms": _safe_float(summary.get("p99_99_latency_ms")),
                "max_latency_ms": _safe_float(summary.get("max_latency_ms")),
                "fail": int(summary.get("fail", 0) or 0),
                "bottleneck": _extract_bottleneck(summary),
                "file": str(out_file),
            }
            rows.append(row)

    # Step 3: bottleneck view
    bottleneck_report = {
        "generated_at": tag,
        "rows": rows,
    }
    (out_dir / f"bottleneck_{tag}.json").write_text(json.dumps(bottleneck_report, indent=2, ensure_ascii=False), encoding="utf-8")

    # choose best concurrency shape from matrix by throughput first
    best = _choose_best_by_throughput(rows)
    best_proc = int(best["processes"])
    best_tpp = int(best["threads_per_process"])

    # Step 5: batch neighborhood search around best shape
    batch_specs = [
        RunSpec(f"p{best_proc}_t{best_tpp}_b128", best_proc, best_tpp, 128),
        RunSpec(f"p{best_proc}_t{best_tpp}_b256", best_proc, best_tpp, 256),
        RunSpec(f"p{best_proc}_t{best_tpp}_b512", best_proc, best_tpp, 512),
        RunSpec(f"p{best_proc}_t{best_tpp}_b1024", best_proc, best_tpp, 1024),
    ]

    batch_rows: list[dict[str, Any]] = []
    for spec in batch_specs:
        out_file = out_dir / f"{spec.name}_{tag}.json"
        summary = _run_stress(repo_root, args.config, args.total, spec, args.chain_mode, out_file)
        batch_rows.append(
            {
                "spec": spec.name,
                "processes": spec.processes,
                "threads_per_process": spec.threads_per_process,
                "batch_size": spec.batch_size,
                "throughput_pps": _safe_float(summary.get("throughput_pps")),
                "p99_99_latency_ms": _safe_float(summary.get("p99_99_latency_ms")),
                "max_latency_ms": _safe_float(summary.get("max_latency_ms")),
                "fail": int(summary.get("fail", 0) or 0),
                "bottleneck": _extract_bottleneck(summary),
                "file": str(out_file),
            }
        )

    summary_doc = {
        "target": target,
        "best_concurrency_candidate": best,
        "batch_candidates": batch_rows,
        "best_batch_candidate": _choose_best_by_throughput(batch_rows),
        "throughput_stats": {
            "baseline_mean": round(statistics.mean([r["throughput_pps"] for r in rows]), 2) if rows else 0.0,
            "baseline_max": round(max([r["throughput_pps"] for r in rows]), 2) if rows else 0.0,
        },
    }

    out_summary = out_dir / f"phase1_summary_{tag}.json"
    out_summary.write_text(json.dumps(summary_doc, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "summary": str(out_summary),
        "best_concurrency": summary_doc["best_concurrency_candidate"]["spec"],
        "best_batch": summary_doc["best_batch_candidate"]["spec"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

