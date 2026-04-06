#!/usr/bin/env python3
"""
OpenSynaptic 本地测试入口
Local Test Runner (NOT included in CI)

用法 / Usage:
  python test.py                    # 运行全部测试套件
  python test.py --suite pytest     # 仅 pytest 单元 + 集成
  python test.py --suite logic      # 仅业务逻辑穷举
  python test.py --suite plugin     # 仅插件穷举
  python test.py --suite infra      # 仅安全基础设施穷举
  python test.py --suite ortho      # 仅正交测试
  python test.py --suite integration # 仅集成脚本
  python test.py --fast             # 跳过耗时 >30s 的套件（pytest + ortho）
  python test.py --list             # 列出所有可用套件
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

REPO  = Path(__file__).resolve().parent
PY    = sys.executable

# ── 颜色 ─────────────────────────────────────────────────────────────────────
_R = "\033[0m"
_G = "\033[32m"
_Y = "\033[33m"
_C = "\033[36m"
_D = "\033[2m"
_RED = "\033[31m"

def _section(text: str) -> None:
    print(f"\n{_C}{'═'*70}\n  {text}\n{'═'*70}{_R}")

def _run(cmd: list[str], cwd: Path = REPO) -> int:
    """运行子进程，实时流式输出，返回退出码"""
    proc = subprocess.Popen(cmd, cwd=str(cwd))
    proc.wait()
    return proc.returncode

# ── 套件定义 ──────────────────────────────────────────────────────────────────
SUITES = {
    "pytest": {
        "label": "pytest  单元 + 集成（tests/）",
        "cmd":   [PY, "-m", "pytest", "tests", "-v", "--tb=short"],
        "fast":  True,
        "timeout_hint": "~15s",
    },
    "integration": {
        "label": "integration_test.py  集成脚本",
        "cmd":   [PY, "-u", "scripts/integration_test.py"],
        "fast":  True,
        "timeout_hint": "~10s",
    },
    "logic": {
        "label": "exhaustive_business_logic.py  业务逻辑穷举（985 项）",
        "cmd":   [PY, "-u", "scripts/exhaustive_business_logic.py"],
        "fast":  False,
        "timeout_hint": "~60s",
    },
    "plugin": {
        "label": "exhaustive_plugin_test.py  插件穷举（205 项）",
        "cmd":   [PY, "-u", "scripts/exhaustive_plugin_test.py"],
        "fast":  False,
        "timeout_hint": "~90s",
    },
    "infra": {
        "label": "exhaustive_security_infra_test.py  安全基础设施穷举（43 项）",
        "cmd":   [PY, "-u", "scripts/exhaustive_security_infra_test.py"],
        "fast":  True,
        "timeout_hint": "~5s",
    },
    "ortho": {
        "label": "exhaustive_orthogonal_test.py  正交测试（24 项）",
        "cmd":   [PY, "-u", "scripts/exhaustive_orthogonal_test.py"],
        "fast":  True,
        "timeout_hint": "~5s",
    },
}

# fast 套件执行顺序（--fast 时使用）
_FAST_ORDER  = ["pytest", "integration", "infra", "ortho"]
# 全量执行顺序
_ALL_ORDER   = ["pytest", "integration", "logic", "plugin", "infra", "ortho"]


def _list_suites() -> None:
    print(f"\n{_C}可用测试套件{_R}\n")
    for key, s in SUITES.items():
        fast_tag = f"{_G}[fast]{_R}" if s["fast"] else f"{_Y}[slow]{_R}"
        print(f"  {_C}{key:<14}{_R} {fast_tag}  {s['label']}  {_D}{s['timeout_hint']}{_R}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OpenSynaptic 本地测试入口（不进 CI）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--suite", "-s", metavar="NAME",
        choices=list(SUITES.keys()),
        help="只运行指定套件",
    )
    parser.add_argument(
        "--fast", "-f", action="store_true",
        help="只运行 fast 套件（跳过 logic / plugin）",
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="列出所有套件后退出",
    )
    args = parser.parse_args()

    if args.list:
        _list_suites()
        return 0

    # 决定要跑哪些套件
    if args.suite:
        run_order = [args.suite]
    elif args.fast:
        run_order = _FAST_ORDER
    else:
        run_order = _ALL_ORDER

    print(f"\n{_C}OpenSynaptic 本地测试入口{_R}")
    print(f"{_D}Python: {PY}{_R}")
    print(f"{_D}仓库:   {REPO}{_R}")
    if args.fast:
        print(f"{_Y}⚡ --fast 模式：跳过 logic / plugin 套件{_R}")

    results: dict[str, tuple[int, float]] = {}
    overall_start = time.perf_counter()

    for key in run_order:
        suite = SUITES[key]
        _section(f"{suite['label']}  [{suite['timeout_hint']}]")
        t0 = time.perf_counter()
        rc = _run(suite["cmd"])
        elapsed = time.perf_counter() - t0
        results[key] = (rc, elapsed)
        status = f"{_G}PASS{_R}" if rc == 0 else f"{_RED}FAIL (exit {rc}){_R}"
        print(f"\n  → {status}  耗时 {elapsed:.1f}s")

    total_elapsed = time.perf_counter() - overall_start

    # ── 摘要 ─────────────────────────────────────────────────────────────────
    print(f"\n{'═'*70}")
    print(f"  {'套件':<40} {'状态':^8}  {'耗时':>6}")
    overall_ok = True
    for key, (rc, elapsed) in results.items():
        ok = rc == 0
        if not ok:
            overall_ok = False
        status_str = f"{_G}PASS{_R}" if ok else f"{_RED}FAIL{_R}"
        print(f"  {SUITES[key]['label']:<40} {status_str}  {elapsed:>5.1f}s")
    print(f"{'═'*70}")
    final_status = f"{_G}ALL PASS{_R}" if overall_ok else f"{_RED}FAILED{_R}"
    print(f"  总耗时: {total_elapsed:.1f}s   结果: {final_status}\n")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
