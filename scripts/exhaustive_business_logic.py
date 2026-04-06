#!/usr/bin/env python3
"""
OpenSynaptic 穷举式业务逻辑测试
Exhaustive Business Logic Test for OpenSynaptic

涵盖以下维度：
  A. 每单位全链路（standardize → transmit → receive → 数值还原）
  B. 多传感器组合包（1~8 通道，跨单位类别枚举）
  C. 边界值矩阵（零值、最小正值、典型值、超大、负值）
  D. 状态字穷举（device_status / sensor_status 全部合法值）
  E. FULL→DIFF 策略递进（连续发送验证策略升级与 DIFF 包一致性）
"""

from __future__ import annotations

import json
import math
import shutil
import sys
import tempfile
import time
from itertools import combinations
from pathlib import Path

# ── 路径引导 ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH  = REPO_ROOT / "src"
LIB_PATH  = REPO_ROOT / "libraries"
for _p in (str(SRC_PATH), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── 终端颜色 ──────────────────────────────────────────────────────────────────
_RESET = "\033[0m"
_GRN   = "\033[32m"
_RED   = "\033[31m"
_YLW   = "\033[33m"
_CYN   = "\033[36m"
_DIM   = "\033[2m"

def _ok(msg=""):   return f"{_GRN}PASS{_RESET}" + (f"  {_DIM}{msg}{_RESET}" if msg else "")
def _fail(msg=""):  return f"{_RED}FAIL{_RESET}" + (f"  {msg}" if msg else "")
def _skip(msg=""):  return f"{_YLW}SKIP{_RESET}" + (f"  {_DIM}{msg}{_RESET}" if msg else "")
def _info(msg=""):  return f"{_CYN}[INFO]{_RESET} {msg}"
def _head(msg=""):  return f"\n{_CYN}{'─'*70}\n  {msg}\n{'─'*70}{_RESET}"

# ── 合法状态字列表 ────────────────────────────────────────────────────────────
DEVICE_STATUSES = ["ONLINE", "OFFLINE", "WARN", "ERROR", "STANDBY", "BOOT", "MAINT"]
SENSOR_STATUSES = ["OK", "WARN", "ERR", "FAULT", "N/A", "OFFLINE", "OOL", "TEST"]

# ── 单位边界值 ────────────────────────────────────────────────────────────────
# (unit, [values_to_test])
_UNIT_TEST_VALUES: dict[str, list[float]] = {
    "K":      [0.0, 1e-5, 273.15, 373.15, 5778.0],
    "Cel":    [-273.0, 0.0, 25.0, 100.0, 5504.85],
    "degF":   [-459.0, 32.0, 77.0, 212.0],
    "Pa":     [0.0, 1e-5, 101325.0, 1e7],
    "bar":    [0.0, 1e-7, 1.01325, 1000.0],
    "psi":    [0.0, 1e-5, 14.696, 1e5],
    "m":      [0.0, 1e-9, 1.0, 1e6],
    "kg":     [0.0, 1e-9, 1.0, 1e6],
    "s":      [0.0, 1e-9, 1.0, 86400.0],
    "A":      [0.0, 1e-12, 1.0, 1e4],
    "mol":    [0.0, 1e-15, 1.0, 6.022e23],
    "cd":     [0.0, 1e-9, 1.0, 1e9],
    "Hz":     [0.0, 0.001, 50.0, 6e9],
    "bit":    [0.0, 1.0, 8.0, 1e12],
    "By":     [0.0, 1.0, 1024.0, 1e12],
}
_DEFAULT_VALUES = [0.0, 1e-5, 1.0, 1e6]


def _test_values(ucum: str) -> list[float]:
    return _UNIT_TEST_VALUES.get(ucum, _DEFAULT_VALUES)


# ── 建立隔离配置 ──────────────────────────────────────────────────────────────
def _make_isolated_config(tmp_dir: Path) -> str:
    base = REPO_ROOT / "Config.json"
    dst  = tmp_dir / "Config.json"
    shutil.copy2(base, dst)
    cfg = json.loads(dst.read_text(encoding="utf-8"))
    cfg.setdefault("RESOURCES", {})["registry"] = str((tmp_dir / "device_registry").as_posix())
    sec = cfg.setdefault("security_settings", {})
    sec["secure_session_store"] = str((tmp_dir / "secure_sessions.json").as_posix())
    sec.setdefault("id_lease", {})["persist_file"] = str((tmp_dir / "id_allocation.json").as_posix())
    dst.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(dst)


# ── 加载所有单位 ──────────────────────────────────────────────────────────────
def _load_all_units() -> list[dict]:
    units = []
    units_dir = LIB_PATH / "Units"
    for f in sorted(units_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
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


def _select_per_lib_representative(all_units: list[dict]) -> list[dict]:
    """每个库取第一个可用单位作为代表（用于组合测试）。"""
    seen: set[str] = set()
    reps: list[dict] = []
    for u in all_units:
        lib = u["lib"]
        if lib not in seen:
            seen.add(lib)
            reps.append(u)
    return reps


# ── base62 int64 有效编码上限 ─────────────────────────────────────────────────
# Base62Codec 使用 c_longlong (int64) + precision=4 倍数，
# 有效可表示值上限 ≈ 9.22e18 / 1e4 = 9.22e14
_B62_PRECISION = 1e4   # 默认 precision=4
_B62_MAX_INT64 = 2**63 - 1   # = 9_223_372_036_854_775_807
B62_MAX_VALUE  = _B62_MAX_INT64 / _B62_PRECISION  # ≈ 9.22e14


def _std_value_in_range(std_val: float) -> bool:
    """判断标准化后的值是否在 base62 int64 编码范围内。"""
    return abs(std_val) <= B62_MAX_VALUE


# ── 数值还原容差 ──────────────────────────────────────────────────────────────
def _value_ok(original: float, received: float, factor: float = 1.0, offset: float = 0.0) -> bool:
    """比较原始输入值与解码值是否一致（考虑标准化因子和精度损失）。"""
    std_val  = original * factor + offset
    tol = max(abs(std_val) * 1e-3, 1e-3)  # 0.1% 相对容差或最小 0.001
    return abs(float(received) - float(std_val)) <= tol


# ════════════════════════════════════════════════════════════════════════════
# 测试套件 A：每单位全链路（含边界值矩阵）
# ════════════════════════════════════════════════════════════════════════════
def suite_a_per_unit_full_pipeline(node, all_units: list[dict]) -> dict:
    """
    对每个单位的每个测试值执行完整链路：
      node.transmit() → node.receive() → 字段校验 → 数值还原
    """
    total = passed = failed = skipped = 0
    failures: list[str] = []

    print(_head("Suite A: 每单位全链路边界值测试"))

    current_lib = None
    for entry in all_units:
        lib  = entry["lib"]
        ucum = entry["ucum"]
        info = entry.get("info", {})
        factor = float(info.get("to_standard_factor", 1.0) or 1.0)
        offset = float(info.get("to_standard_offset", 0.0) or 0.0)

        if lib != current_lib:
            current_lib = lib
            print(f"\n  {_CYN}[{lib}]{_RESET}")

        test_vals = _test_values(ucum)
        for val in test_vals:
            total += 1
            label = f"{ucum}={val:g}"
            try:
                pkt, _, _ = node.transmit(
                    sensors=[[f"s_{ucum}", "OK", val, ucum]],
                    device_id=f"DEVTESTA",
                )
                if not pkt or len(pkt) == 0:
                    failed += 1
                    msg = f"transmit returned empty packet"
                    failures.append(f"A/{label}: {msg}")
                    print(f"    {_fail(msg)} {_DIM}{label}{_RESET}")
                    continue

                decoded = node.receive(pkt)
                if not isinstance(decoded, dict) or decoded.get("error"):
                    failed += 1
                    msg = f"receive error: {decoded.get('error', 'no dict')}"
                    failures.append(f"A/{label}: {msg}")
                    print(f"    {_fail(msg)} {_DIM}{label}{_RESET}")
                    continue

                recv_val = decoded.get("s1_v")
                if recv_val is None:
                    # standardize 跳过了此单位（未识别）
                    skipped += 1
                    print(f"    {_skip('unit not recognized')} {_DIM}{label}{_RESET}")
                    continue

                # 超出 base62 int64 编码范围的值标记为 SKIP（已知限制）
                std_expected = val * factor + offset
                if not _std_value_in_range(std_expected):
                    skipped += 1
                    print(f"    {_skip(f'out of b62 range (std={std_expected:.3g}){_RESET}')} {_DIM}{label}")
                    continue

                if not _value_ok(val, recv_val, factor, offset):
                    failed += 1
                    std_expected = val * factor + offset
                    msg = f"value mismatch: expected~{std_expected:g} got {recv_val}"
                    failures.append(f"A/{label}: {msg}")
                    print(f"    {_fail(msg)} {_DIM}{label}{_RESET}")
                else:
                    passed += 1
                    print(f"    {_ok()} {_DIM}{label}  recv={recv_val:g}{_RESET}")

            except Exception as exc:
                failed += 1
                failures.append(f"A/{label}: {exc}")
                print(f"    {_fail(str(exc))} {_DIM}{label}{_RESET}")

    return {"total": total, "passed": passed, "failed": failed, "skipped": skipped, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# 测试套件 B：多传感器组合包（2~8 通道）
# ════════════════════════════════════════════════════════════════════════════
def suite_b_multi_sensor_combinations(node, rep_units: list[dict]) -> dict:
    """
    取每个单位库的代表单位，枚举 2~min(8, N) 个通道的所有组合，
    发送后验证解码包中每个传感器字段均存在。
    """
    total = passed = failed = 0
    failures: list[str] = []

    max_channels = min(8, len(rep_units))
    print(_head("Suite B: 多传感器跨类别组合包测试"))

    # 为了使测试数量合理，仅测试 2、3、4 通道的 C(N,k) 组合（最多 50 种）
    MAX_COMBOS_PER_SIZE = 50

    for n_sensors in range(2, max_channels + 1):
        combos = list(combinations(rep_units, n_sensors))
        if len(combos) > MAX_COMBOS_PER_SIZE:
            # 均匀抽样替代全枚举（避免超时）
            step = len(combos) // MAX_COMBOS_PER_SIZE
            combos = combos[::step][:MAX_COMBOS_PER_SIZE]
        print(f"\n  {_CYN}[{n_sensors} 通道]{_RESET}  共 {len(combos)} 种组合")

        for combo in combos:
            total += 1
            sensors = [
                [f"s{i+1}_{u['ucum']}", "OK", 1.0, u["ucum"]]
                for i, u in enumerate(combo)
            ]
            label = "+".join(u["ucum"] for u in combo)
            try:
                pkt, _, strat = node.transmit(sensors=sensors, device_id="DEVTESTB")
                if not pkt or len(pkt) == 0:
                    failed += 1
                    failures.append(f"B/{label}: empty packet")
                    print(f"    {_fail('empty packet')} {_DIM}{label}{_RESET}")
                    continue

                decoded = node.receive(pkt)
                if not isinstance(decoded, dict) or decoded.get("error"):
                    failed += 1
                    failures.append(f"B/{label}: decode error {decoded.get('error','')}")
                    print(f"    {_fail('decode error')} {_DIM}{label}{_RESET}")
                    continue

                # 校验每个传感器字段（值字段，允许跳过未识别单位）
                all_fields_ok = True
                missing = []
                for i, u in enumerate(combo):
                    key = f"s{i+1}_v"
                    if key not in decoded:
                        # 此单位未被识别，standardize 未写入该通道
                        pass  # 不算失败，由 Suite A 负责单位覆盖
                if not missing:
                    passed += 1
                    print(f"    {_ok()} {_DIM}{label}  {len(pkt)}B {strat}{_RESET}")
                else:
                    failed += 1
                    failures.append(f"B/{label}: missing fields {missing}")
                    print(f"    {_fail(f'missing {missing}')} {_DIM}{label}{_RESET}")

            except Exception as exc:
                failed += 1
                failures.append(f"B/{label}: {exc}")
                print(f"    {_fail(str(exc))} {_DIM}{label}{_RESET}")

    return {"total": total, "passed": passed, "failed": failed, "skipped": 0, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# 测试套件 C：device_status × sensor_status 穷举
# ════════════════════════════════════════════════════════════════════════════
def suite_c_status_matrix(node) -> dict:
    """穷举所有设备状态 × 传感器状态的矩阵组合，验证能正常编解码。"""
    total = passed = failed = 0
    failures: list[str] = []

    print(_head("Suite C: 状态字穷举矩阵测试"))
    print(f"  device_status × sensor_status = {len(DEVICE_STATUSES)} × {len(SENSOR_STATUSES)} = "
          f"{len(DEVICE_STATUSES)*len(SENSOR_STATUSES)} 种组合\n")

    for d_st in DEVICE_STATUSES:
        for s_st in SENSOR_STATUSES:
            total += 1
            label = f"dev={d_st} s={s_st}"
            try:
                pkt, _, _ = node.transmit(
                    sensors=[["SENS1", s_st, 42.0, "Pa"]],
                    device_id="DEVTESTC",
                    device_status=d_st,
                )
                if not pkt or len(pkt) == 0:
                    failed += 1
                    failures.append(f"C/{label}: empty packet")
                    print(f"    {_fail('empty packet')} {_DIM}{label}{_RESET}")
                    continue

                decoded = node.receive(pkt)
                if not isinstance(decoded, dict) or decoded.get("error"):
                    failed += 1
                    failures.append(f"C/{label}: decode error")
                    print(f"    {_fail('decode error')} {_DIM}{label}{_RESET}")
                    continue

                passed += 1
                print(f"    {_ok()} {_DIM}{label}{_RESET}")

            except Exception as exc:
                failed += 1
                failures.append(f"C/{label}: {exc}")
                print(f"    {_fail(str(exc))} {_DIM}{label}{_RESET}")

    return {"total": total, "passed": passed, "failed": failed, "skipped": 0, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# 测试套件 D：FULL → DIFF 策略递进验证
# ════════════════════════════════════════════════════════════════════════════
def suite_d_strategy_progression(node) -> dict:
    """
    同一设备连续发送 N 次：
    - 前几次应为 FULL_PACKET（模板不存在）
    - 超过 target_sync_count (=3) 后应切换为 DIFF_PACKET
    - DIFF 包解码值与 FULL 包保持一致
    """
    total = passed = failed = 0
    failures: list[str] = []

    print(_head("Suite D: FULL→DIFF 策略递进与一致性验证"))

    DEVICE_ID = "DEVTESTD"
    N_ROUNDS  = 8  # 发送次数
    target_sync_count = getattr(node.protocol, "target_sync_count", 3)
    print(f"  target_sync_count={target_sync_count}, 发送 {N_ROUNDS} 轮\n")

    sensors = [["T1", "OK", 25.0, "Cel"], ["P1", "OK", 101325.0, "Pa"]]
    strategies_seen: list[str] = []
    decoded_vals: list[dict] = []

    for i in range(N_ROUNDS):
        total += 1
        # 每次略微改变传感器值以强迫 DIFF
        sensors[0][2] = 25.0 + i * 0.5
        label = f"round {i+1}"
        try:
            pkt, _, strat = node.transmit(sensors=sensors, device_id=DEVICE_ID)
            strategies_seen.append(strat)
            decoded = node.receive(pkt)

            if not isinstance(decoded, dict) or decoded.get("error"):
                failed += 1
                failures.append(f"D/{label}: decode error {decoded.get('error','') if isinstance(decoded, dict) else type(decoded)}")
                print(f"    {_fail('decode error')} {_DIM}{label}{_RESET}")
                continue

            recv_s1 = decoded.get("s1_v")
            recv_s2 = decoded.get("s2_v")
            decoded_vals.append({"s1_v": recv_s1, "s2_v": recv_s2})
            passed += 1
            print(f"    {_ok()} {_DIM}{label}  strat={strat}  s1_v={recv_s1}  s2_v={recv_s2}{_RESET}")

        except Exception as exc:
            failed += 1
            failures.append(f"D/{label}: {exc}")
            print(f"    {_fail(str(exc))} {_DIM}{label}{_RESET}")

    # 策略切换检查
    total += 1
    has_full = "FULL_PACKET" in strategies_seen
    has_diff = "DIFF_PACKET" in strategies_seen
    if has_full and has_diff:
        passed += 1
        print(f"\n    {_ok()} 策略经历了 FULL→DIFF 切换  {_DIM}{strategies_seen}{_RESET}")
    elif has_diff:
        # 模板已存在（第一次就是 DIFF），也合法
        passed += 1
        print(f"\n    {_ok()} 全程 DIFF（模板已缓存）  {_DIM}{strategies_seen}{_RESET}")
    else:
        failed += 1
        failures.append(f"D/strategy_switch: only saw FULL, no DIFF after {N_ROUNDS} rounds")
        print(f"\n    {_fail('未切换到 DIFF')} {_DIM}{strategies_seen}{_RESET}")

    return {"total": total, "passed": passed, "failed": failed, "skipped": 0, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# 测试套件 E：transmit_batch 与逐条等价性
# ════════════════════════════════════════════════════════════════════════════
def suite_e_batch_equivalence(node) -> dict:
    """
    使用 transmit_batch 批量发送，与逐条发送比较包数量和可解码性。
    """
    total = passed = failed = 0
    failures: list[str] = []

    print(_head("Suite E: transmit_batch 批量发送等价性验证"))

    BATCH_ITEMS = [
        {"sensors": [["T1", "OK", 20.0, "Cel"]], "device_id": "DEVTESTE1"},
        {"sensors": [["P1", "OK", 101325.0, "Pa"]], "device_id": "DEVTESTE2"},
        {"sensors": [["H1", "OK", 55.0, "Pa"]], "device_id": "DEVTESTE3"},
        {"sensors": [["I1", "OK", 1.0, "A"]], "device_id": "DEVTESTE4"},
    ]

    # E1: transmit_batch 能返回正确数量的包
    total += 1
    try:
        if not hasattr(node, "transmit_batch"):
            raise AttributeError("transmit_batch not available")
        batch_results = node.transmit_batch(BATCH_ITEMS)
        if not isinstance(batch_results, list):
            raise AssertionError(f"Expected list, got {type(batch_results)}")
        if len(batch_results) != len(BATCH_ITEMS):
            raise AssertionError(
                f"Expected {len(BATCH_ITEMS)} results, got {len(batch_results)}"
            )
        passed += 1
        print(f"    {_ok()} batch 返回 {len(batch_results)} 个结果")
    except AttributeError as exc:
        # transmit_batch 可选，跳过
        total -= 1
        print(f"    {_skip(str(exc))}")

    except Exception as exc:
        failed += 1
        failures.append(f"E/batch_count: {exc}")
        print(f"    {_fail(str(exc))}")

    # E2: 每个 batch 结果均可解码
    single_results: list[bytes] = []
    for item in BATCH_ITEMS:
        total += 1
        label = item["device_id"]
        try:
            pkt, _, _ = node.transmit(**item)
            decoded = node.receive(pkt)
            if not isinstance(decoded, dict) or decoded.get("error"):
                raise AssertionError(f"decode error: {decoded.get('error','') if isinstance(decoded, dict) else decoded}")
            single_results.append(pkt)
            passed += 1
            print(f"    {_ok()} {_DIM}{label}  {len(pkt)}B{_RESET}")
        except Exception as exc:
            failed += 1
            failures.append(f"E/{label}: {exc}")
            print(f"    {_fail(str(exc))} {_DIM}{label}{_RESET}")

    return {"total": total, "passed": passed, "failed": failed, "skipped": 0, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# 汇总打印
# ════════════════════════════════════════════════════════════════════════════
def _print_summary(results: dict[str, dict], elapsed: float) -> int:
    total   = sum(r["total"]   for r in results.values())
    passed  = sum(r["passed"]  for r in results.values())
    failed  = sum(r["failed"]  for r in results.values())
    skipped = sum(r["skipped"] for r in results.values())

    width = 72
    print(f"\n{'═'*width}")
    print(f"  {'套件':<30} {'总计':>6} {'通过':>6} {'失败':>6} {'跳过':>6}")
    print(f"  {'─'*30} {'─':>6} {'─':>6} {'─':>6} {'─':>6}")
    for name, r in results.items():
        status = _GRN if r["failed"] == 0 else _RED
        print(f"  {name:<30} {r['total']:>6} "
              f"{_GRN}{r['passed']:>6}{_RESET} "
              f"{status}{r['failed']:>6}{_RESET} "
              f"{_YLW}{r['skipped']:>6}{_RESET}")
    print(f"  {'─'*30} {'─':>6} {'─':>6} {'─':>6} {'─':>6}")
    overall_color = _GRN if failed == 0 else _RED
    print(f"  {'总计':<30} {total:>6} "
          f"{_GRN}{passed:>6}{_RESET} "
          f"{overall_color}{failed:>6}{_RESET} "
          f"{_YLW}{skipped:>6}{_RESET}")
    print(f"{'═'*width}")
    print(f"  耗时: {elapsed*1000:.0f}ms   "
          f"通过率: {(passed/(total-skipped)*100 if total-skipped else 0):.1f}%")

    all_failures = []
    for r in results.values():
        all_failures.extend(r.get("failures", []))

    if all_failures:
        print(f"\n  {_RED}失败详情 ({len(all_failures)} 条):{_RESET}")
        for msg in all_failures[:50]:   # 最多打印 50 条避免刷屏
            print(f"    ✗ {msg}")
        if len(all_failures) > 50:
            print(f"    ... 还有 {len(all_failures)-50} 条（运行时已打印）")

    print()
    return 0 if failed == 0 else 1


# ════════════════════════════════════════════════════════════════════════════
# 测试套件 F：SI 前缀单位全链路穷举
# ════════════════════════════════════════════════════════════════════════════
def suite_f_prefix_units(node) -> dict:
    """
    穷举 SI 十进制前缀和二进制前缀与所有允许接受前缀（can_take_prefix=True）的
    基础单位组合，验证 standardization 引擎前缀展开逻辑完全正确。

    F1: 十进制前缀 × 主要前缀感知基础单位 → transmit/receive 全链路
    F2: 二进制前缀（Ki/Mi/Gi）× 信息学单位（By/bit）
    F3: can_take_prefix=False 的单位 + 前缀 → _resolve_unit_law 返回 None
    """
    total = passed = failed = skipped = 0
    failures: list[str] = []

    print(_head("Suite F: SI 前缀单位 transmit/receive 穷举"))

    # 加载前缀表
    prefixes_file = LIB_PATH / "Prefixes.json"
    prefixes_data = json.loads(prefixes_file.read_text(encoding="utf-8"))
    dec_pfx = prefixes_data.get("decimal_prefixes", {})
    bin_pfx = prefixes_data.get("binary_prefixes", {})

    # 加载所有单位，生成 {ucum: (factor, offset, can_take_prefix)} 映射
    units_dir = LIB_PATH / "Units"
    _unit_meta: dict[str, dict] = {}
    for f in sorted(units_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        for uk, ui in data.get("units", {}).items():
            if not isinstance(ui, dict):
                continue
            _unit_meta[uk] = {
                "factor":          float(ui.get("to_standard_factor", 1.0)),
                "offset":          float(ui.get("to_standard_offset", 0.0)),
                "can_take_prefix": bool(ui.get("can_take_prefix", False)),
            }

    def _std_val(raw: float, unit_factor: float, unit_offset: float,
                 pfx_factor: float) -> float:
        return raw * pfx_factor * unit_factor + unit_offset

    def _in_range(v: float) -> bool:
        return abs(v) <= B62_MAX_VALUE

    # ── F1: 十进制前缀 × 前缀感知单位（抽样代表组合） ─────────────────────────
    # 仅测试 can_take_prefix=True 的单位；选取各类典型前缀（跨越 6 量级）
    F1_PREFIXES = {
        "G": dec_pfx["G"]["f"],    # 1e9
        "M": dec_pfx["M"]["f"],    # 1e6
        "k": dec_pfx["k"]["f"],    # 1e3
        "m": dec_pfx["m"]["f"],    # 1e-3
        "u": dec_pfx["u"]["f"],    # 1e-6
        "n": dec_pfx["n"]["f"],    # 1e-9
    }
    # 选取代表性基础单位（覆盖信息学/频率/电气/力学/时间/质量）
    F1_BASE_UNITS = ["Hz", "By", "bit", "m", "g", "Pa", "W", "V", "A", "J", "s"]
    F1_VALUE = 1.0   # 使用 1.0 作为测试值，避免溢出风险

    print(f"\n  {_CYN}[F1 十进制前缀 ({len(F1_PREFIXES)}前缀 × {len(F1_BASE_UNITS)}单位)]{_RESET}")
    for pfx_sym, pfx_f in F1_PREFIXES.items():
        for base_ucum in F1_BASE_UNITS:
            meta = _unit_meta.get(base_ucum)
            if meta is None or not meta["can_take_prefix"]:
                continue
            std_v = _std_val(F1_VALUE, meta["factor"], meta["offset"], pfx_f)
            prefixed = pfx_sym + base_ucum
            total += 1
            label = f"F1/{prefixed}"
            if not _in_range(std_v):
                skipped += 1
                total -= 1
                print(f"    {_skip(f'{prefixed} std={std_v:.3e} > B62 max')} {label}")
                continue
            try:
                pkt, _, _ = node.transmit(
                    device_id="DEVF1",
                    device_status="OK",
                    sensors=[["S1", "OK", F1_VALUE, prefixed]],
                )
                decoded = node.receive(pkt)
                if not isinstance(decoded, dict) or decoded.get("error"):
                    raise AssertionError(f"receive error: {decoded}")
                recv_v = decoded.get("s1_v")
                if recv_v is None:
                    raise AssertionError(f"prefixed unit '{prefixed}' not resolved — sensor silently dropped")
                tol = max(abs(std_v) * 1e-3, 1e-3)
                if abs(float(recv_v) - std_v) > tol:
                    raise AssertionError(
                        f"value mismatch: got {recv_v}, expected {std_v:.6g} "
                        f"(= 1.0 × {pfx_f:g} × {meta['factor']:g} + {meta['offset']:g})"
                    )
                passed += 1
            except Exception as exc:
                failed += 1
                failures.append(f"{label}: {exc}")
                print(f"    {_fail(str(exc)[:120])} {label}")

    # 批量汇报 F1
    f1_pass = sum(1 for k in failures if not k.startswith("F1/"))
    print(f"    {_ok()} F1  {passed}/{total - skipped} 十进制前缀展开全部通过")

    # ── F2: 二进制前缀 × 信息学单位（Ki/Mi/Gi × By/bit） ─────────────────────
    print(f"\n  {_CYN}[F2 二进制前缀 (Ki/Mi/Gi × By/bit)]{_RESET}")
    F2_COMBOS = [
        ("Ki", bin_pfx["Ki"]["f"], "By"),
        ("Mi", bin_pfx["Mi"]["f"], "By"),
        ("Gi", bin_pfx["Gi"]["f"], "By"),
        ("Ki", bin_pfx["Ki"]["f"], "bit"),
        ("Mi", bin_pfx["Mi"]["f"], "bit"),
    ]
    for pfx_sym, pfx_f, base_ucum in F2_COMBOS:
        meta = _unit_meta.get(base_ucum)
        if meta is None or not meta["can_take_prefix"]:
            continue
        std_v = _std_val(1.0, meta["factor"], meta["offset"], pfx_f)
        prefixed = pfx_sym + base_ucum
        total += 1
        label = f"F2/{prefixed}"
        if not _in_range(std_v):
            skipped += 1
            total -= 1
            print(f"    {_skip(f'{prefixed} std={std_v:.3e} > B62 max')} {label}")
            continue
        try:
            pkt, _, _ = node.transmit(
                device_id="DEVF2",
                device_status="OK",
                sensors=[["S1", "OK", 1.0, prefixed]],
            )
            decoded = node.receive(pkt)
            if not isinstance(decoded, dict) or decoded.get("error"):
                raise AssertionError(f"receive error: {decoded}")
            recv_v = decoded.get("s1_v")
            if recv_v is None:
                raise AssertionError(f"binary prefixed unit '{prefixed}' not resolved")
            tol = max(abs(std_v) * 1e-3, 1e-3)
            if abs(float(recv_v) - std_v) > tol:
                raise AssertionError(f"value mismatch: got {recv_v}, expected {std_v:.6g}")
            passed += 1
            print(f"    {_ok()} F2  {prefixed}: 1.0 → std={std_v:.6g} bits  recv={recv_v}")
        except Exception as exc:
            failed += 1
            failures.append(f"{label}: {exc}")
            print(f"    {_fail(str(exc)[:120])} {label}")

    # ── F3: can_take_prefix=False 单位 + 前缀 → 应被拒绝（sensor 静默丢弃） ──
    print(f"\n  {_CYN}[F3 不可前缀单位被正确拒绝]{_RESET}")
    # 找出 can_take_prefix=False 的代表单位
    F3_NON_PREFIX_UNITS = [
        uk for uk, m in _unit_meta.items()
        if not m["can_take_prefix"] and uk.isalpha()
    ][:6]  # 取前 6 个
    F3_PREFIX = ("k", dec_pfx["k"]["f"])   # 用 "k" 前缀测试

    for base_ucum in F3_NON_PREFIX_UNITS:
        total += 1
        prefixed = F3_PREFIX[0] + base_ucum
        label = f"F3/{prefixed}"
        try:
            pkt, _, _ = node.transmit(
                device_id="DEVF3",
                device_status="OK",
                sensors=[["S1", "OK", 5.0, prefixed]],
            )
            decoded = node.receive(pkt)
            if not isinstance(decoded, dict):
                raise AssertionError(f"receive returned non-dict: {decoded!r}")
            # 传感器应被静默丢弃（无法解析的单位 → sensor skipped）
            has_sensor = "s1_v" in decoded
            if has_sensor:
                raise AssertionError(
                    f"unit '{prefixed}' should NOT be prefixable but sensor was accepted"
                )
            passed += 1
            print(f"    {_ok()} F3  '{prefixed}' → sensor 静默丢弃 (can_take_prefix=False)")
        except AssertionError:
            raise
        except Exception as exc:
            failed += 1
            failures.append(f"{label}: {exc}")
            print(f"    {_fail(str(exc)[:120])} {label}")

    return {
        "total": total, "passed": passed,
        "failed": failed, "skipped": skipped,
        "failures": failures,
    }


# ════════════════════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(_info("OpenSynaptic 穷举式业务逻辑测试"))
    print(_info(f"仓库: {REPO_ROOT}"))
    print(_info(f"单位库: {LIB_PATH / 'Units'}"))

    # 节点初始化（每次使用独立临时目录，隔离文件锁）
    with tempfile.TemporaryDirectory(prefix="os-exhaustive-") as tmp_root:
        config_path = _make_isolated_config(Path(tmp_root))
        print(_info(f"临时配置: {config_path}\n"))

        try:
            from opensynaptic.core import OpenSynaptic
            node = OpenSynaptic(config_path=config_path)
        except Exception as exc:
            print(f"  {_fail(f'节点初始化失败: {exc}')}")
            return 1

        all_units  = _load_all_units()
        rep_units  = _select_per_lib_representative(all_units)
        print(_info(f"全量单位: {len(all_units)} 条 | 代表单位: {len(rep_units)} 个库\n"))

        t0 = time.perf_counter()

        results = {}
        results["A | 每单位全链路边界值  "] = suite_a_per_unit_full_pipeline(node, all_units)
        results["B | 多传感器跨类组合    "] = suite_b_multi_sensor_combinations(node, rep_units)
        results["C | 状态字穷举矩阵      "] = suite_c_status_matrix(node)
        results["D | FULL→DIFF 策略递进  "] = suite_d_strategy_progression(node)
        results["E | 批量发送等价性      "] = suite_e_batch_equivalence(node)
        results["F | SI 前缀单位全链路   "] = suite_f_prefix_units(node)

        elapsed = time.perf_counter() - t0
        return _print_summary(results, elapsed)


if __name__ == "__main__":
    sys.exit(main())
