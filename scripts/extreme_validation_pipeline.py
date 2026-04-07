#!/usr/bin/env python3
"""Comprehensive OpenSynaptic validation pipeline.

This runner orchestrates core/build checks, plugin suites, transport stress,
protocol audits, and CLI/service smoke coverage. It writes a machine-readable
report so results are reproducible and comparable across runs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Step:
    step_id: str
    description: str
    gate: str
    timeout_s: int
    cmd: list[str]


def _tail(text: str, limit: int = 6000) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[-limit:]


def _cmd(*parts: str) -> list[str]:
    return [*parts]


def _scale_profile(scale: str) -> dict[str, int]:
    if scale == "smoke":
        return {
            "compare_total": 5000,
            "core_total": 10000,
            "e2e_inproc_total": 5000,
            "e2e_udp_total": 3000,
            "e2e_tcp_total": 2000,
            "workers": 8,
            "processes": 2,
            "batch": 32,
        }
    if scale == "extreme":
        return {
            "compare_total": 50000,
            "core_total": 200000,
            "e2e_inproc_total": 50000,
            "e2e_udp_total": 30000,
            "e2e_tcp_total": 15000,
            "workers": 16,
            "processes": 4,
            "batch": 64,
        }
    return {
        "compare_total": 20000,
        "core_total": 50000,
        "e2e_inproc_total": 20000,
        "e2e_udp_total": 10000,
        "e2e_tcp_total": 5000,
        "workers": 16,
        "processes": 4,
        "batch": 64,
    }


def build_steps(py: str, scale: str) -> list[Step]:
    p = _scale_profile(scale)

    steps = [
        Step(
            step_id="core-status",
            description="Core backend visibility",
            gate="required",
            timeout_s=60,
            cmd=_cmd(py, "-u", "src/main.py", "core", "--json"),
        ),
        Step(
            step_id="native-check",
            description="Toolchain preflight",
            gate="required",
            timeout_s=120,
            cmd=_cmd(py, "-u", "src/main.py", "native-check", "--json", "--timeout", "20"),
        ),
        Step(
            step_id="native-build",
            description="C ABI build verification",
            gate="required",
            timeout_s=900,
            cmd=_cmd(py, "-u", "src/main.py", "native-build", "--json"),
        ),
        Step(
            step_id="rscore-check",
            description="Rust backend availability",
            gate="required",
            timeout_s=120,
            cmd=_cmd(py, "-u", "src/main.py", "rscore-check", "--json"),
        ),
        Step(
            step_id="rscore-build",
            description="Rust ABI build verification",
            gate="required",
            timeout_s=1200,
            cmd=_cmd(py, "-u", "src/main.py", "rscore-build", "--json", "--no-progress"),
        ),
        Step(
            step_id="runtime-discovery",
            description="Status + snapshot + transporter map",
            gate="required",
            timeout_s=240,
            cmd=_cmd(py, "-u", "src/main.py", "snapshot"),
        ),
        Step(
            step_id="plugin-lifecycle",
            description="Plugin list + load",
            gate="required",
            timeout_s=120,
            cmd=_cmd(py, "-u", "src/main.py", "plugin-load", "--name", "tui"),
        ),
        Step(
            step_id="port-forwarder-status",
            description="Port forwarder plugin status check",
            gate="required",
            timeout_s=120,
            cmd=_cmd(
                py,
                "-u",
                "src/main.py",
                "plugin-cmd",
                "--plugin",
                "port_forwarder",
                "--cmd",
                "status",
            ),
        ),
        Step(
            step_id="port-forwarder-list",
            description="Port forwarder rule list check",
            gate="required",
            timeout_s=120,
            cmd=_cmd(
                py,
                "-u",
                "src/main.py",
                "plugin-cmd",
                "--plugin",
                "port_forwarder",
                "--cmd",
                "list",
            ),
        ),
        Step(
            step_id="port-forwarder-roundtrip",
            description="Port forwarder add/list/remove/list loopback check",
            gate="required",
            timeout_s=180,
            cmd=_cmd(py, "-u", "scripts/port_forwarder_roundtrip_check.py"),
        ),
        Step(
            step_id="port-forwarder-matrix-sim",
            description="Port forwarder exhaustive local protocol matrix simulation",
            gate="required",
            timeout_s=300,
            cmd=_cmd(py, "-u", "scripts/port_forwarder_matrix_sim_check.py"),
        ),
        Step(
            step_id="doctor-self-heal",
            description="Diagnostics and self-heal",
            gate="required",
            timeout_s=120,
            cmd=_cmd(py, "-u", "src/main.py", "doctor", "--json", "--self-heal"),
        ),
        Step(
            step_id="component-parallel",
            description="Component tests in parallel/process mode",
            gate="required",
            timeout_s=900,
            cmd=_cmd(
                py,
                "-u",
                "src/main.py",
                "plugin-test",
                "--suite",
                "component",
                "--parallel-component",
                "--component-processes",
                "4",
                "--max-class-workers",
                "4",
                "--verbosity",
                "1",
            ),
        ),
        Step(
            step_id="plugin-integration",
            description="Plugin integration suite",
            gate="required",
            timeout_s=300,
            cmd=_cmd(py, "-u", "src/main.py", "plugin-test", "--suite", "integration"),
        ),
        Step(
            step_id="plugin-audit",
            description="Plugin driver capability audit suite",
            gate="required",
            timeout_s=300,
            cmd=_cmd(py, "-u", "src/main.py", "plugin-test", "--suite", "audit"),
        ),
        Step(
            step_id="backend-compare",
            description="pycore vs rscore stress comparison",
            gate="required",
            timeout_s=1800,
            cmd=_cmd(
                py,
                "-u",
                "src/main.py",
                "plugin-test",
                "--suite",
                "compare",
                "--total",
                str(p["compare_total"]),
                "--workers",
                str(p["workers"]),
                "--processes",
                str(p["processes"]),
                "--batch-size",
                str(p["batch"]),
                "--runs",
                "3",
                "--warmup",
                "1",
                "--pipeline-mode",
                "batch_fused",
                "--json-out",
                "data/benchmarks/compare_extreme_latest.json",
            ),
        ),
        Step(
            step_id="stress-core-pycore",
            description="Core stress (pycore)",
            gate="required",
            timeout_s=1800,
            cmd=_cmd(
                py,
                "-u",
                "src/main.py",
                "plugin-test",
                "--suite",
                "stress",
                "--total",
                str(p["core_total"]),
                "--workers",
                str(p["workers"]),
                "--processes",
                str(p["processes"]),
                "--batch-size",
                str(p["batch"]),
                "--core-backend",
                "pycore",
                "--chain-mode",
                "core",
                "--pipeline-mode",
                "legacy",
                "--no-progress",
                "--json-out",
                "data/benchmarks/stress_core_pycore_extreme_latest.json",
            ),
        ),
        Step(
            step_id="stress-core-rscore",
            description="Core stress (rscore)",
            gate="required",
            timeout_s=1800,
            cmd=_cmd(
                py,
                "-u",
                "src/main.py",
                "plugin-test",
                "--suite",
                "stress",
                "--total",
                str(p["core_total"]),
                "--workers",
                str(p["workers"]),
                "--processes",
                str(p["processes"]),
                "--batch-size",
                str(p["batch"]),
                "--core-backend",
                "rscore",
                "--require-rust",
                "--chain-mode",
                "core",
                "--pipeline-mode",
                "batch_fused",
                "--no-progress",
                "--json-out",
                "data/benchmarks/stress_core_rscore_extreme_latest.json",
            ),
        ),
        Step(
            step_id="stress-e2e-inproc",
            description="E2E in-process stress",
            gate="required",
            timeout_s=1800,
            cmd=_cmd(
                py,
                "-u",
                "src/main.py",
                "plugin-test",
                "--suite",
                "stress",
                "--total",
                str(p["e2e_inproc_total"]),
                "--workers",
                "8",
                "--processes",
                "2",
                "--batch-size",
                "32",
                "--core-backend",
                "pycore",
                "--chain-mode",
                "e2e_inproc",
                "--pipeline-mode",
                "legacy",
                "--no-progress",
                "--json-out",
                "data/benchmarks/stress_e2e_inproc_pycore_latest.json",
            ),
        ),
        Step(
            step_id="stress-e2e-udp",
            description="E2E loopback UDP stress",
            gate="required",
            timeout_s=1800,
            cmd=_cmd(
                py,
                "-u",
                "src/main.py",
                "plugin-test",
                "--suite",
                "stress",
                "--total",
                str(p["e2e_udp_total"]),
                "--workers",
                "8",
                "--processes",
                "1",
                "--batch-size",
                "16",
                "--core-backend",
                "pycore",
                "--chain-mode",
                "e2e_loopback",
                "--use-transport",
                "udp",
                "--pipeline-mode",
                "legacy",
                "--no-progress",
                "--json-out",
                "data/benchmarks/stress_e2e_loopback_udp_latest.json",
            ),
        ),
        Step(
            step_id="stress-e2e-tcp",
            description="E2E loopback TCP stress",
            gate="required",
            timeout_s=1800,
            cmd=_cmd(
                py,
                "-u",
                "src/main.py",
                "plugin-test",
                "--suite",
                "stress",
                "--total",
                str(p["e2e_tcp_total"]),
                "--workers",
                "8",
                "--processes",
                "1",
                "--batch-size",
                "16",
                "--core-backend",
                "pycore",
                "--chain-mode",
                "e2e_loopback",
                "--use-transport",
                "tcp",
                "--pipeline-mode",
                "legacy",
                "--no-progress",
                "--json-out",
                "data/benchmarks/stress_e2e_loopback_tcp_latest.json",
            ),
        ),
        Step(
            step_id="integration-script",
            description="Standalone integration script",
            gate="required",
            timeout_s=600,
            cmd=_cmd(py, "-u", "scripts/integration_test.py"),
        ),
        Step(
            step_id="pytest-cov",
            description="Pytest unit/integration with coverage",
            gate="required",
            timeout_s=1200,
            cmd=_cmd(py, "-m", "pytest", "--cov=opensynaptic", "tests"),
        ),
        Step(
            step_id="driver-audit-script",
            description="Driver capability audit script",
            gate="required",
            timeout_s=1200,
            cmd=_cmd(py, "-u", "scripts/audit_driver_capabilities.py"),
        ),
        Step(
            step_id="protocol-matrix",
            description="Exhaustive protocol interoperability matrix",
            gate="required",
            timeout_s=1200,
            cmd=_cmd(
                py,
                "-u",
                "scripts/protocol_matrix_exhaustive.py",
                "--host",
                "127.0.0.1",
                "--base-port",
                "19180",
                "--timeout",
                "1.5",
            ),
        ),
        Step(
            step_id="services-smoke",
            description="Service plugin smoke checks",
            gate="required",
            timeout_s=1200,
            cmd=_cmd(py, "-u", "scripts/services_smoke_check.py"),
        ),
        Step(
            step_id="cli-exhaustive",
            description="CLI command surface exhaustive check",
            gate="required",
            timeout_s=2400,
            cmd=_cmd(py, "-u", "scripts/cli_exhaustive_check.py"),
        ),
    ]

    return steps


def _profile_steps(steps: list[Step], profile: str) -> list[Step]:
    return steps


def run_step(step: Step, cwd: Path) -> dict[str, Any]:
    started_at = time.time()
    try:
        proc = subprocess.run(
            step.cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=step.timeout_s,
        )
        elapsed = round(time.time() - started_at, 3)
        ok = proc.returncode == 0
        return {
            "step_id": step.step_id,
            "description": step.description,
            "gate": step.gate,
            "ok": ok,
            "returncode": int(proc.returncode),
            "timed_out": False,
            "elapsed_s": elapsed,
            "command": step.cmd,
            "stdout_tail": _tail(proc.stdout or ""),
            "stderr_tail": _tail(proc.stderr or ""),
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = round(time.time() - started_at, 3)
        return {
            "step_id": step.step_id,
            "description": step.description,
            "gate": step.gate,
            "ok": False,
            "returncode": -1,
            "timed_out": True,
            "elapsed_s": elapsed,
            "command": step.cmd,
            "stdout_tail": _tail(exc.stdout if isinstance(exc.stdout, str) else ""),
            "stderr_tail": _tail(exc.stderr if isinstance(exc.stderr, str) else ""),
            "error": f"timeout after {step.timeout_s}s",
        }
    except Exception as exc:  # pragma: no cover
        elapsed = round(time.time() - started_at, 3)
        return {
            "step_id": step.step_id,
            "description": step.description,
            "gate": step.gate,
            "ok": False,
            "returncode": -1,
            "timed_out": False,
            "elapsed_s": elapsed,
            "command": step.cmd,
            "stdout_tail": "",
            "stderr_tail": "",
            "error": str(exc),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run comprehensive OpenSynaptic validation pipeline")
    parser.add_argument(
        "--scale",
        choices=["smoke", "full", "extreme"],
        default="full",
        help="Workload scale for stress/compare stages",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit non-zero if any step fails (default: only required steps fail build)",
    )
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        default=False,
        help="Stop immediately when a step fails",
    )
    parser.add_argument(
        "--profile",
        choices=["primary", "global"],
        default="primary",
        help="Pipeline profile label for report/CI routing; both primary and global run the full suite",
    )
    parser.add_argument(
        "--output",
        default="data/benchmarks/extreme_validation_report_latest.json",
        help="Output JSON report path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    output_path = (repo_root / args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    py = sys.executable
    steps = _profile_steps(build_steps(py=py, scale=args.scale), profile=args.profile)

    started = time.time()
    results: list[dict[str, Any]] = []

    print("=" * 88)
    print("OpenSynaptic Extreme Validation Pipeline")
    print("=" * 88)
    print(f"Profile: {args.profile}")
    print(f"Scale: {args.scale}")
    print(f"Python: {py}")
    print(f"Steps: {len(steps)}")

    for idx, step in enumerate(steps, start=1):
        print(f"\n[{idx}/{len(steps)}] {step.step_id} ({step.gate})")
        print(f"  {step.description}")
        result = run_step(step, cwd=repo_root)
        results.append(result)

        status = "PASS" if result["ok"] else "FAIL"
        print(
            f"  -> {status} rc={result['returncode']} elapsed={result['elapsed_s']:.3f}s"
            + (" timeout" if result.get("timed_out") else "")
        )

        if args.stop_on_fail and not result["ok"]:
            print("  stop-on-fail enabled: aborting further steps")
            break

    elapsed_total = round(time.time() - started, 3)

    failed = [r for r in results if not r["ok"]]
    required_failed = [r for r in failed if r.get("gate") == "required"]

    report = {
        "runner": "extreme_validation_pipeline",
        "profile": args.profile,
        "scale": args.scale,
        "python": py,
        "started_epoch": started,
        "elapsed_s": elapsed_total,
        "total_steps": len(results),
        "passed_steps": len(results) - len(failed),
        "failed_steps": len(failed),
        "required_failed_steps": len(required_failed),
        "strict": bool(args.strict),
        "stop_on_fail": bool(args.stop_on_fail),
        "steps": results,
    }
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 88)
    print(
        "Summary: "
        f"passed={report['passed_steps']} failed={report['failed_steps']} "
        f"required_failed={report['required_failed_steps']} elapsed={elapsed_total:.3f}s"
    )
    print(f"Report: {output_path}")

    if args.strict and failed:
        return 1
    if required_failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
