#!/usr/bin/env python3
"""
OpenSynaptic Library Validation Suite
验证 SymbolHarvester、OS_Registry 及 Device Operations 单位库的正确性。
"""

import sys
import json
from pathlib import Path

# ── 路径引导 ──────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH  = REPO_ROOT / "src"
for p in (str(SRC_PATH), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# ── 颜色输出 ──────────────────────────────────────────────────────────────────
OK   = "\033[32m[PASS]\033[0m"
FAIL = "\033[31m[FAIL]\033[0m"
INFO = "\033[36m[INFO]\033[0m"

results = []

def check(name, expr, expected=True, info=""):
    ok = bool(expr) == bool(expected)
    tag = OK if ok else FAIL
    suffix = f"  ({info})" if info else ""
    print(f"  {tag} {name}{suffix}")
    results.append((name, ok))
    return ok


def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SymbolHarvester
# ═══════════════════════════════════════════════════════════════════════════════
section("1 / 3  SymbolHarvester (harvester.py)")

try:
    from libraries.harvester import SymbolHarvester
    h = SymbolHarvester()
    symbol_data = h.sync()

    check("sync() 返回非空 dict",        isinstance(symbol_data, dict) and len(symbol_data) > 0)
    check("'units' 键存在",              "units" in symbol_data)
    check("'states' 键存在",             "states" in symbol_data)
    check("units 包含温度类符号",         any("temperature" in k or "Cel" in k or "K" in k
                                              for k in symbol_data.get("units", {})))
    check("states 包含 online/offline",  "online" in symbol_data.get("states", {})
                                          and "offline" in symbol_data.get("states", {}))

    ops_symbols = {k: v for k, v in symbol_data.get("units", {}).items()
                   if "operations" in k.lower() or k in ("cmd", "pow.on", "mv.up")}
    check("Operations 单位库被纳入 sync()",
          any(k.lower() == "operations" for k in symbol_data.get("units", {})),
          info=f"operations key present: {list(ops_symbols.keys())[:5]}")

except Exception as e:
    print(f"  {FAIL} SymbolHarvester 初始化或 sync() 异常: {e}")
    results.append(("SymbolHarvester 整体", False))


# ═══════════════════════════════════════════════════════════════════════════════
# 2. OS_Registry
# ═══════════════════════════════════════════════════════════════════════════════
section("2 / 3  OS_Registry (OS_Registry.py)")

try:
    from libraries.OS_Registry import OS_Registry
    reg = OS_Registry()

    # ── 2a. 基础索引 ──────────────────────────────────────────────────────────
    check("atomic_map 非空",              len(reg.atomic_map) > 0,
          info=f"{len(reg.atomic_map)} classes")
    check("ucum_to_id 非空",              len(reg.ucum_to_id) > 0)
    check("unit_detail_map 非空",         len(reg.unit_detail_map) > 0,
          info=f"{len(reg.unit_detail_map)} units total")
    check("unit_detail_map ≥ atomic_map", len(reg.unit_detail_map) >= len(reg.atomic_map))

    # ── 2b. 物理单位查询不受影响 ─────────────────────────────────────────────
    k_info = reg.lookup("K")
    cel_info = reg.lookup("Cel")
    check("lookup('K') 返回温度基准单位",
          k_info is not None and k_info.get("physical_attribute") == "temperature")
    check("lookup('Cel') 返回摄氏度单位",
          cel_info is not None and float(cel_info.get("to_standard_offset", 0)) == 273.15,
          info="offset=273.15")

    # ── 2c. resolve() / compose() 矩阵编码不受影响 ──────────────────────────
    byte1, byte2 = reg.compose("K", prefix="k")
    check("compose('K', prefix='k') 成功", byte1 is not None and byte2 is not None,
          info=f"byte1={hex(byte1) if byte1 else None}, byte2={hex(byte2) if byte2 else None}")
    if byte1 is not None:
        info_out, label = reg.resolve(byte1, byte2)
        check("resolve() 还原为 kK",      label == "kK", info=f"got '{label}'")

    # ── 2d. 操作指令新索引 ───────────────────────────────────────────────────
    ops_cases = [
        ("cmd",     "operation",       None),
        ("pow.on",  "power_control",   False),
        ("pow.off", "power_control",   False),
        ("set.val", "parameter_write", True),
        ("get.val", "parameter_read",  False),
        ("get.st",  "status_query",    False),
        ("rst",     "device_control",  False),
        ("mv.up",   "motion_control",  False),
        ("mv.dn",   "motion_control",  False),
        ("mv.lt",   "motion_control",  False),
        ("mv.rt",   "motion_control",  False),
        ("stp",     "motion_control",  False),
        ("stp.e",   "safety_control",  False),
        ("mv.to",   "motion_control",  True),
        ("rot.cw",  "rotation_control",False),
        ("rot.cc",  "rotation_control",False),
        ("cmdA",    "user_defined",    False),
        ("cmdZ",    "user_defined",    False),
        ("modeA",   "mode_select",     False),
        ("modeZ",   "mode_select",     False),
    ]
    op_pass = 0
    op_fail = []
    for ucum, exp_attr, exp_req in ops_cases:
        info_d = reg.lookup(ucum)
        if info_d is None:
            op_fail.append(f"{ucum}:not_found")
            continue
        if info_d.get("physical_attribute") != exp_attr:
            op_fail.append(f"{ucum}:attr={info_d.get('physical_attribute')}")
            continue
        if exp_req is not None and info_d.get("requires_value") != exp_req:
            op_fail.append(f"{ucum}:req_val={info_d.get('requires_value')}")
            continue
        op_pass += 1

    check(f"操作指令 lookup() 全部通过 ({op_pass}/{len(ops_cases)})",
          len(op_fail) == 0,
          info=", ".join(op_fail) if op_fail else "all ok")

except Exception as e:
    print(f"  {FAIL} OS_Registry 初始化异常: {e}")
    results.append(("OS_Registry 整体", False))


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Device Operations JSON 格式验证
# ═══════════════════════════════════════════════════════════════════════════════
section("3 / 3  Device Operations JSON 格式验证")

ops_json_path = REPO_ROOT / "libraries" / "Units" / "Opensynaptic_Ucum_Device_Operations.json"

try:
    with open(ops_json_path, "r", encoding="utf-8") as fh:
        ops_data = json.load(fh)

    meta  = ops_data.get("__METADATA__", {})
    units = ops_data.get("units", {})

    check("JSON 可正常解析",              True)
    check("__METADATA__ 存在",            bool(meta))
    check("class_id = 0x0E",              meta.get("class_id") == "0x0E")
    check("OS_UNIT_SYMBOLS = 'D'",        meta.get("OS_UNIT_SYMBOLS") == "D")
    check("base_unit = 'cmd'",            meta.get("base_unit") == "cmd")

    # tid 唯一性
    tids = [v.get("tid") for v in units.values()]
    check("所有 tid 唯一",                len(tids) == len(set(tids)),
          info=f"{len(tids)} entries")

    # ucum_code 与 key 一致性
    mismatch = [k for k, v in units.items() if v.get("ucum_code") != k]
    check("ucum_code 与 key 一致",        len(mismatch) == 0,
          info=f"mismatch: {mismatch}" if mismatch else "all ok")

    # 必填字段完整性
    required_fields = ("name", "ucum_code", "tid", "physical_attribute",
                       "standard_unit_name", "to_standard_factor",
                       "can_take_prefix", "direction", "requires_value", "description")
    missing = {k: [f for f in required_fields if f not in v]
               for k, v in units.items() if any(f not in v for f in required_fields)}
    check("所有 unit 必填字段完整",        len(missing) == 0,
          info=f"missing in: {list(missing.keys())}" if missing else "all ok")

    # direction 值合法
    bad_dir = [k for k, v in units.items() if v.get("direction") not in ("read", "write")]
    check("direction 值均为 read/write",  len(bad_dir) == 0,
          info=f"bad: {bad_dir}" if bad_dir else "all ok")

    # 预留槽位数量
    cmd_slots  = [k for k in units if k.startswith("cmd") and len(k) == 4 and k[3].isalpha()]
    mode_slots = [k for k in units if k.startswith("mode") and len(k) == 5 and k[4].isalpha()]
    check(f"cmdA-Z 预留槽 26 条",         len(cmd_slots) == 26,  info=f"found {len(cmd_slots)}")
    check(f"modeA-Z 预留槽 26 条",        len(mode_slots) == 26, info=f"found {len(mode_slots)}")

    print(f"\n  {INFO} 共 {len(units)} 条操作指令")

except Exception as e:
    print(f"  {FAIL} Device Operations JSON 验证异常: {e}")
    results.append(("Device Operations JSON 整体", False))


# ═══════════════════════════════════════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════════════════════════════════════
section("汇总")
total  = len(results)
passed = sum(1 for _, ok in results if ok)
failed = total - passed

for name, ok in results:
    print(f"  {'✓' if ok else '✗'}  {name}")

print(f"\n  结果: {passed}/{total} 通过", end="")
if failed:
    print(f"  ← {failed} 项失败")
    sys.exit(1)
else:
    print("  ✓ 全部通过")
    sys.exit(0)
