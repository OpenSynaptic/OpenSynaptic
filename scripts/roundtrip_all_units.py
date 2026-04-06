#!/usr/bin/env python3
"""
OpenSynaptic Full Unit Roundtrip Test
对所有单位库中的每条 unit 执行 standardize → compress → decompress 本地收发验证。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# ── 路径引导 ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH  = REPO_ROOT / "src"
LIB_PATH  = REPO_ROOT / "libraries"
for p in (str(SRC_PATH), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ── 颜色 ─────────────────────────────────────────────────────────────────────
OK   = "\033[32m PASS\033[0m"
FAIL = "\033[31m FAIL\033[0m"
SKIP = "\033[33m SKIP\033[0m"
INFO = "\033[36m[INFO]\033[0m"

# ── 单位测试值表（对特殊单位给定合理初始值） ─────────────────────────────────
_DEFAULT_VAL = 1.0
_VALUE_HINTS: dict[str, float] = {
    "Cel":    25.0,    # 摄氏度 → +273.15 → K
    "degF":   77.0,    # 华氏度
    "degRe":  20.0,    # 列氏度
    "K":      298.15,
    "m":      1.0,
    "kg":     1.0,
    "s":      1.0,
    "A":      1.0,
    "cd":     1.0,
    "mol":    1.0,
    "Pa":     101325.0,
    "Hz":     50.0,
    "bit":    8.0,
    "By":     1.0,
}


def _test_val(ucum: str) -> float:
    return _VALUE_HINTS.get(ucum, _DEFAULT_VAL)


def _load_all_units() -> list[dict]:
    """从 libraries/Units/ 读取所有 JSON，返回扁平化的单位列表。"""
    units = []
    units_dir = LIB_PATH / "Units"
    for f in sorted(units_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"{FAIL} 无法解析 {f.name}: {e}")
            continue
        meta     = data.get("__METADATA__", {})
        lib_name = meta.get("standard_name", f.stem)
        class_id = meta.get("class_id", "?")
        for u_key, u_info in data.get("units", {}).items():
            units.append({
                "lib":      lib_name,
                "class_id": class_id,
                "ucum":     u_key,
                "info":     u_info,
            })
    return units


def _roundtrip_one(std, eng, unit_entry: dict) -> tuple[bool, str, dict]:
    """
    执行单条 unit 的完整 standardize → compress → decompress 流程。
    返回 (ok, detail_msg, result_dict)
    """
    ucum   = unit_entry["ucum"]
    val    = _test_val(ucum)
    s_id   = f"SEN-{ucum.replace('.', '_')}"
    s_stat = "online"

    # ── 1. standardize ────────────────────────────────────────────────────────
    try:
        fact = std.standardize(
            device_id=f"DEV-TEST",
            device_status=s_stat,
            sensors=[(s_id, s_stat, val, ucum)],
        )
    except Exception as e:
        return False, f"standardize error: {e}", {}

    if not fact or "s1_v" not in fact:
        return False, "standardize returned no sensor data (unit not recognized)", {"fact": fact}

    # ── 2. compress ───────────────────────────────────────────────────────────
    try:
        packet = eng.compress(fact)
    except Exception as e:
        return False, f"compress error: {e}", {"fact": fact}

    if not isinstance(packet, str) or not packet:
        return False, f"compress returned invalid packet: {packet!r}", {"fact": fact}

    # ── 3. decompress ─────────────────────────────────────────────────────────
    try:
        recovered = eng.decompress(packet)
    except Exception as e:
        return False, f"decompress error: {e}", {"fact": fact, "packet": packet}

    if not isinstance(recovered, dict) or "s1_v" not in recovered:
        return False, f"decompress returned no s1_v: {recovered}", {"fact": fact, "packet": packet}

    # ── 4. 数值一致性校验 ─────────────────────────────────────────────────────
    std_val   = fact["s1_v"]
    recv_val  = recovered["s1_v"]
    tolerance = max(abs(std_val) * 1e-4, 1e-4)
    val_ok = abs(float(recv_val) - float(std_val)) <= tolerance

    detail = {
        "input_val":  val,
        "std_val":    std_val,
        "recv_val":   recv_val,
        "std_unit":   fact.get("s1_u"),
        "recv_unit":  recovered.get("s1_u"),
        "packet_len": len(packet),
    }
    if not val_ok:
        return False, f"value mismatch: std={std_val} recv={recv_val}", detail
    return True, "ok", detail


def main() -> int:
    # ── 引擎初始化 ────────────────────────────────────────────────────────────
    config_path = str(REPO_ROOT / "src" / "Config.json")
    if not Path(config_path).exists():
        config_path = str(REPO_ROOT / "Config.json")

    units_dir = str(REPO_ROOT / "libraries" / "Units")

    try:
        from opensynaptic.core.pycore.standardization import OpenSynapticStandardizer
        from opensynaptic.core.pycore.solidity         import OpenSynapticEngine
        std = OpenSynapticStandardizer(config_path=config_path if Path(config_path).exists() else None)
        eng = OpenSynapticEngine(config_path=config_path if Path(config_path).exists() else None)

        # ── 覆盖标准化引擎的单位库路径（Config.json 中的 RESOURCES.root 不指向实际库）
        std.lib_units_dir = units_dir
        std._units_by_key.clear()
        std._units_by_ucum.clear()
        std._build_unit_indices()

        # ── 让压缩引擎也指向正确的符号文件
        sym_path = str(REPO_ROOT / "libraries" / "OS_Symbols.json")
        if Path(sym_path).exists():
            eng.sym_path = sym_path
            eng._symbols_cache = None
            eng._refresh_maps()

    except Exception as e:
        print(f"{FAIL} 引擎初始化失败: {e}")
        return 1

    # ── 加载所有单位 ──────────────────────────────────────────────────────────
    all_units = _load_all_units()
    print(f"\n{INFO} 共加载 {len(all_units)} 条单位，开始逐一收发验证...\n")

    # ── 按 lib 分组打印 ────────────────────────────────────────────────────────
    passed = 0
    failed = 0
    skipped = 0
    failures: list[tuple[str, str, str]] = []

    current_lib = None
    lib_stats: dict[str, dict] = {}

    t0 = time.perf_counter()

    for entry in all_units:
        lib   = entry["lib"]
        ucum  = entry["ucum"]
        cid   = entry["class_id"]

        if lib != current_lib:
            current_lib = lib
            print(f"  ── {lib} ({cid}) ──")
            lib_stats[lib] = {"pass": 0, "fail": 0, "skip": 0}

        ok, msg, detail = _roundtrip_one(std, eng, entry)

        if ok:
            passed += 1
            lib_stats[lib]["pass"] += 1
            std_u  = detail.get("std_unit", "?")
            recv_u = detail.get("recv_unit", "?")
            print(f"    {OK}  {ucum:<16} "
                  f"in={detail['input_val']:>10g}  "
                  f"→ std={detail['std_val']:>12g} [{std_u}]  "
                  f"→ recv={detail['recv_val']:>12g} [{recv_u}]  "
                  f"pkt={detail['packet_len']}B")
        elif "not recognized" in msg:
            skipped += 1
            lib_stats[lib]["skip"] += 1
            print(f"    {SKIP}  {ucum:<16} {msg}")
        else:
            failed += 1
            lib_stats[lib]["fail"] += 1
            failures.append((lib, ucum, msg))
            print(f"    {FAIL}  {ucum:<16} {msg}")

    elapsed = time.perf_counter() - t0

    # ── 汇总 ──────────────────────────────────────────────────────────────────
    width = 60
    print(f"\n{'═'*width}")
    print(f"  {'库名':<50} {'P':>4} {'F':>4} {'S':>4}")
    print(f"  {'─'*50} {'─':>4} {'─':>4} {'─':>4}")
    for lib, s in lib_stats.items():
        short = lib[-48:] if len(lib) > 48 else lib
        print(f"  {short:<50} {s['pass']:>4} {s['fail']:>4} {s['skip']:>4}")
    print(f"{'═'*width}")
    print(f"  总计: {passed+failed+skipped} 条  "
          f"\033[32m通过: {passed}\033[0m  "
          f"\033[31m失败: {failed}\033[0m  "
          f"\033[33m跳过: {skipped}\033[0m  "
          f"耗时: {elapsed*1000:.1f}ms")

    if failures:
        print(f"\n  失败详情:")
        for lib, ucum, msg in failures:
            print(f"    ✗  [{lib}] {ucum}: {msg}")

    print()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
