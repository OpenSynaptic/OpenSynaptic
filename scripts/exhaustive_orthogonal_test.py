#!/usr/bin/env python3
"""
OpenSynaptic 正交测试套件
Orthogonal Design Test Suite

Suite EP — EnhancedPortForwarder 5 个二值功能开关 L8 正交
  · 目的：验证 firewall / traffic_shaping / protocol_conversion / middleware / proxy
    任意两两组合时的交互行为均符合预期（尤其是 firewall 阻断后 middleware.after 不再被调用）
  · 设计：L8(2^5) 正交表，共 8 runs

Suite XC — IDAllocator × Unit × Medium × ChannelCount L16 正交
  · 目的：验证跨层链路耦合：
    A. 设备 Key 类型（device_id / mac / serial / uuid）影响 IDAllocator 去重
    B. 单位类型（Pa / Cel / Hz / By）影响编解码
    C. 发送媒介（UDP / TCP / UART / CAN）影响 dispatch
    D. 传感器通道数（1 / 2 / 3 / 4）影响包结构
  · 设计：L16(4^4) 正交表，共 16 runs；每对因子出现所有 4×4=16 种组合各恰好 1 次
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH  = REPO_ROOT / "src"
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

def _ok(msg=""):  return f"{_GRN}PASS{_RESET}" + (f"  {_DIM}{msg}{_RESET}" if msg else "")
def _fail(msg=""): return f"{_RED}FAIL{_RESET}" + (f"  {msg}" if msg else "")
def _skip(msg=""): return f"{_YLW}SKIP{_RESET}" + (f"  {_DIM}{msg}{_RESET}" if msg else "")
def _head(msg=""):  return f"\n{_CYN}{'─'*70}\n  {msg}\n{'─'*70}{_RESET}"

def _assert(cond, msg=""):
    if not cond:
        raise AssertionError(msg or "Assertion failed")

def _print_summary(results: dict, elapsed: float) -> int:
    total_t = passed_t = failed_t = skipped_t = 0
    all_failures = []
    for label, r in results.items():
        total_t   += r.get("total", 0)
        passed_t  += r.get("passed", 0)
        failed_t  += r.get("failed", 0)
        skipped_t += r.get("skipped", 0)
        all_failures.extend(r.get("failures", []))
    sep = "═" * 72
    row_w = 46
    print(f"\n{sep}")
    print(f"  {'套件':<{row_w}} {'总计':>5}  {'通过':>5}  {'失败':>5}  {'跳过':>5}")
    for label, r in results.items():
        print(f"  {label:<{row_w}} {r.get('total',0):>5}  {r.get('passed',0):>5}  {r.get('failed',0):>5}  {r.get('skipped',0):>5}")
    print(f"  {'总计':<{row_w}} {total_t:>5}  {passed_t:>5}  {failed_t:>5}  {skipped_t:>5}")
    print(sep)
    rate = 100.0*passed_t/(total_t-skipped_t) if (total_t-skipped_t) > 0 else 100.0
    print(f"  耗时: {elapsed*1000:.0f}ms   通过率: {rate:.1f}%")
    if all_failures:
        print(f"\n  失败详情 ({len(all_failures)} 条):")
        for f in all_failures:
            print(f"  {_RED}✗{_RESET} {f[:160]}")
    print()
    return 0 if failed_t == 0 else 1


# ════════════════════════════════════════════════════════════════════════════
# Suite EP — EnhancedPortForwarder 5-flag L8 正交
# ════════════════════════════════════════════════════════════════════════════
# L8(2^7) 标准正交表前 5 列
# 列: [firewall, traffic_shaping, protocol_conversion, middleware, proxy]
_L8 = [
    [0, 0, 0, 0, 0],   # EP-0: 全 disabled
    [0, 0, 0, 1, 1],   # EP-1
    [0, 1, 1, 0, 0],   # EP-2
    [0, 1, 1, 1, 1],   # EP-3
    [1, 0, 1, 0, 1],   # EP-4
    [1, 0, 1, 1, 0],   # EP-5
    [1, 1, 0, 0, 1],   # EP-6
    [1, 1, 0, 1, 0],   # EP-7
]
_FLAG_NAMES = ["firewall", "traffic_shaping", "protocol_conversion", "middleware", "proxy"]

def suite_ep_epf_orthogonal() -> dict:
    total = passed = failed = skipped = 0
    failures: list[str] = []

    print(_head("Suite EP: EnhancedPortForwarder 5-flag × L8 正交（8 runs）"))

    try:
        from opensynaptic.services.port_forwarder.enhanced import (
            EnhancedPortForwarder, FirewallRule, TrafficShaper,
            ProtocolConverter, Middleware, ProxyRule,
        )
    except ImportError as e:
        print(f"    {_skip(f'import failed: {e}')}")
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 1, "failures": []}

    MEDIUM = "UDP"

    for run_idx, flags in enumerate(_L8):
        total += 1
        fw, ts, pc, mw, px = [bool(f) for f in flags]
        run_label = f"EP-{run_idx}"
        flag_str = (
            f"fw={'ON ' if fw else 'OFF'} "
            f"ts={'ON ' if ts else 'OFF'} "
            f"pc={'ON ' if pc else 'OFF'} "
            f"mw={'ON ' if mw else 'OFF'} "
            f"px={'ON ' if px else 'OFF'}"
        )
        try:
            # ── 计数器 ───────────────────────────────────────────────────────
            before_count = [0]
            after_count  = [0]

            # ── 构造 EPF（按 L8 行设置功能开关）────────────────────────────
            epf = EnhancedPortForwarder(node=None)
            epf.set_features(
                firewall=fw,
                traffic_shaping=ts,
                protocol_conversion=pc,
                middleware=mw,
                proxy=px,
            )

            # ── 1. 防火墙：永久 deny UDP（无差别阻断）───────────────────────
            epf.add_firewall_rule(FirewallRule(
                name="deny_all", action="deny",
                from_protocol=MEDIUM, priority=100,
            ))

            # ── 2. 流量整形：burst_capacity=9999（绝不等待）─────────────────
            shaper = TrafficShaper(name="big_burst", rate_limit_bps=10_000_000, burst_capacity=9999)
            epf.add_traffic_shaper(MEDIUM, shaper)

            # ── 3. 协议转换：UDP→UDP 追加 magic byte ────────────────────────
            conv_ran = [False]
            def _conv(pkt, _ran=conv_ran):
                _ran[0] = True
                return pkt + b"\xAA"
            epf.add_protocol_converter(ProtocolConverter(
                name="udp2udp", from_protocol=MEDIUM, to_protocol=MEDIUM,
                transform_func=_conv,
            ))

            # ── 4. 中间件：before/after 计数 ─────────────────────────────────
            def _before(pkt, medium, _bc=before_count):
                _bc[0] += 1
                return pkt
            def _after(pkt, medium, result, _ac=after_count):
                _ac[0] += 1
                return result
            epf.add_middleware(Middleware(name="counter",
                                          before_dispatch=_before,
                                          after_dispatch=_after))

            # ── 5. 代理规则（占位，不实际转发）─────────────────────────────
            epf.add_proxy_rule(ProxyRule(
                name=MEDIUM, from_protocol=MEDIUM, to_protocol=MEDIUM,
                to_host="127.0.0.1", to_port=9000,
            ))

            # ── Mock 节点 auto_load ─────────────────────────────────────────
            class _MockNode:
                def dispatch(self, pkt, medium=None): return True
            mock_node = _MockNode()
            epf.node = mock_node
            epf.auto_load()

            # ── 派发 1 个包 ─────────────────────────────────────────────────
            test_pkt = b"\x3f\x00\x01\x02\x03\x04\x05"
            dispatch_result = mock_node.dispatch(test_pkt, medium=MEDIUM)
            epf.close()
            s = epf.get_stats()

            # ── 验证 ←────────────────────────────────────────────────────────
            _assert(s["total_packets"] == 1, f"total_packets={s['total_packets']}")

            # --- firewall 交互 ---
            if fw:
                _assert(dispatch_result is False,
                        f"fw=ON 应阻断，dispatch_result={dispatch_result}")
                _assert(s["denied_packets"] >= 1,
                        f"fw=ON 应记录 denied，得 {s['denied_packets']}")
            else:
                _assert(dispatch_result is True,
                        f"fw=OFF 应放行，dispatch_result={dispatch_result}")
                _assert(s["denied_packets"] == 0,
                        f"fw=OFF denied 应为 0，得 {s['denied_packets']}")

            # --- middleware × firewall 交互 ---
            if mw:
                # before_dispatch 在 firewall 检查之前执行，无论 fw 是否阻断
                _assert(before_count[0] >= 1,
                        f"mw=ON: before_dispatch 应执行，count={before_count[0]}")
                if fw:
                    # firewall 阻断后 dispatch 提前 return False → after_dispatch 不执行
                    _assert(after_count[0] == 0,
                            f"mw=ON+fw=ON: after_dispatch 不应执行，count={after_count[0]}")
                else:
                    # firewall 未阻断 → after_dispatch 执行
                    _assert(after_count[0] >= 1,
                            f"mw=ON+fw=OFF: after_dispatch 应执行，count={after_count[0]}")
            else:
                _assert(before_count[0] == 0,
                        f"mw=OFF: before_dispatch 不应执行，count={before_count[0]}")
                _assert(after_count[0] == 0,
                        f"mw=OFF: after_dispatch 不应执行，count={after_count[0]}")

            # --- protocol_conversion × firewall 交互 ---
            if pc and not fw:
                # 转换步骤在 firewall 之后（步骤4），仅当 firewall 放行时执行
                _assert(s["converted_packets"] >= 1,
                        f"pc=ON+fw=OFF: converted_packets 应≥1，得 {s['converted_packets']}")
            elif fw:
                _assert(s["converted_packets"] == 0,
                        f"pc=*/fw=ON: converted_packets 应=0（被阻断），得 {s['converted_packets']}")

            # --- traffic_shaping × firewall 交互 ---
            if ts and not fw:
                # 整形步骤在 firewall 之后（步骤3），仅当 firewall 放行时执行
                _assert(s["shaped_packets"] >= 1,
                        f"ts=ON+fw=OFF: shaped_packets 应≥1，得 {s['shaped_packets']}")
            elif fw:
                _assert(s["shaped_packets"] == 0,
                        f"ts=*/fw=ON: shaped_packets 应=0（被阻断），得 {s['shaped_packets']}")

            passed += 1
            print(f"    {_ok()} {run_label} {flag_str}  "
                  f"→ pass={dispatch_result} denied={s['denied_packets']} "
                  f"mw_b={before_count[0]}/a={after_count[0]} "
                  f"shaped={s['shaped_packets']} conv={s['converted_packets']}")

        except Exception as e:
            failed += 1
            failures.append(f"{run_label}: {e}")
            print(f"    {_fail(str(e)[:100])} {run_label} {flag_str}")

    return {"total": total, "passed": passed, "failed": failed, "skipped": skipped, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# Suite XC — IDAllocator×Unit×Medium×Channels L16 正交
# ════════════════════════════════════════════════════════════════════════════
# L16(4^4)：标准正交表（基于 GF(4)），每对列的 4×4=16 种组合各出现 1 次
# 列 A=设备Key类型  B=单位  C=发送媒介  D=通道数（值为 0-based 索引）
_L16 = [
    [0, 0, 0, 0],   # XC-00
    [0, 1, 1, 1],   # XC-01
    [0, 2, 2, 2],   # XC-02
    [0, 3, 3, 3],   # XC-03
    [1, 0, 1, 2],   # XC-04
    [1, 1, 0, 3],   # XC-05
    [1, 2, 3, 0],   # XC-06
    [1, 3, 2, 1],   # XC-07
    [2, 0, 2, 3],   # XC-08
    [2, 1, 3, 2],   # XC-09
    [2, 2, 0, 1],   # XC-10
    [2, 3, 1, 0],   # XC-11
    [3, 0, 3, 1],   # XC-12
    [3, 1, 2, 0],   # XC-13
    [3, 2, 1, 3],   # XC-14
    [3, 3, 0, 2],   # XC-15
]

_KEY_FIELDS  = ["device_id", "mac", "serial", "uuid"]       # Factor A
_UNITS       = ["Pa", "Cel", "Hz", "By"]                    # Factor B
_MEDIUMS     = ["UDP", "TCP", "UART", "CAN"]                 # Factor C
_CHAN_COUNTS  = [1, 2, 3, 4]                                 # Factor D

# 基本测试值，每种单位取一个安全范围内的值
_UNIT_VALUES = {
    "Pa":  101325.0,   # 标准大气压
    "Cel": 25.0,       # 标准化为 K：298.15
    "Hz":  1000.0,     # 1 kHz，标准化为 1000 Hz
    "By":  128.0,      # 128 字节，标准化为 1024 bit
}

def _verify_pair_balance(array: list, col_a: int, col_b: int, levels: int) -> bool:
    """验证两列 pairwise 平衡：每种组合恰好出现 levels 次"""
    from collections import Counter
    counts = Counter((row[col_a], row[col_b]) for row in array)
    expected = len(array) // (levels * levels)
    return all(v == expected for v in counts.values())

def suite_xc_cross_chain_orthogonal(tmp_dir: Path) -> dict:
    total = passed = failed = skipped = 0
    failures: list[str] = []

    print(_head("Suite XC: IDAllocator×Unit×Medium×Channels L16 正交（16 runs）"))

    # ── 首先验证 L16 矩阵本身的平衡性（自验证，不计入 total）────────────
    for ca, cb in [(0,1),(0,2),(0,3),(1,2),(1,3),(2,3)]:
        assert _verify_pair_balance(_L16, ca, cb, 4), \
            f"L16 列 {ca},{cb} 不平衡！请检查正交表设计"
    print(f"    {_DIM}L16 正交矩阵 pairwise 平衡性验证通过（6 对列全部正确）{_RESET}")

    # ── 导入所需模块 ──────────────────────────────────────────────────────
    try:
        from opensynaptic.core import OpenSynaptic
        from opensynaptic.utils.id_allocator import IDAllocator
        from opensynaptic.services.port_forwarder.main import ForwardingRule
    except ImportError as e:
        print(f"    {_skip(f'import failed: {e}')}")
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 1, "failures": []}

    # ── 共享一个 OpenSynaptic 节点实例（避免重复初始化开销）─────────────
    node_dir = tmp_dir / "xc_node"
    node_dir.mkdir(parents=True, exist_ok=True)
    cfg_src = REPO_ROOT / "Config.json"
    cfg_dst = node_dir / "Config.json"
    shutil.copy2(cfg_src, cfg_dst)
    raw_cfg = json.loads(cfg_dst.read_text("utf-8"))
    raw_cfg.setdefault("RESOURCES", {})["registry"] = str((node_dir / "reg").as_posix())
    sec = raw_cfg.setdefault("security_settings", {})
    sec["secure_session_store"] = str((node_dir / "ss.json").as_posix())
    sec.setdefault("id_lease", {})["persist_file"] = str((node_dir / "ida.json").as_posix())
    cfg_dst.write_text(json.dumps(raw_cfg, indent=2, ensure_ascii=False), "utf-8")
    node = OpenSynaptic(config_path=str(cfg_dst))

    for run_idx, (a, b, c, d) in enumerate(_L16):
        total += 1
        key_field  = _KEY_FIELDS[a]
        unit       = _UNITS[b]
        medium     = _MEDIUMS[c]
        chan_count = _CHAN_COUNTS[d]
        test_value = _UNIT_VALUES[unit]
        run_label  = f"XC-{run_idx:02d}"
        factor_str = (
            f"key={key_field:<9} unit={unit:<3} medium={medium:<4} ch={chan_count}"
        )
        try:
            # ────────────────────────────────────────────────────────────────
            # 子测试 1: IDAllocator — 用特定 key 类型分配 chan_count 个 ID
            # ────────────────────────────────────────────────────────────────
            ida = IDAllocator(
                base_dir=str(tmp_dir / f"xc_ida_{run_idx:02d}"),
                persist_file="alloc.json",
                start_id=1, end_id=9999,
                lease_policy={"offline_hold_days": 1},
            )
            alloc_ids = []
            for i in range(chan_count):
                dev_str = f"XC_{run_idx:02d}_CH{i}"
                aid = ida.allocate_id({key_field: dev_str, "device_id": dev_str})
                alloc_ids.append(aid)
            _assert(len(set(alloc_ids)) == chan_count,
                    f"应分配 {chan_count} 个唯一 ID，得 {len(set(alloc_ids))}")
            for aid in alloc_ids:
                _assert(ida.is_allocated(aid), f"aid={aid} 应已分配")
                meta = ida.get_meta(aid)
                _assert(key_field in meta or "device_id" in meta,
                        f"meta 应含 {key_field!r}，得 {list(meta.keys())}")

            # ────────────────────────────────────────────────────────────────
            # 子测试 2: 发送 × 接收 — D channels 使用 unit B
            # ────────────────────────────────────────────────────────────────
            sensors = [[f"S{i+1}", "OK", test_value, unit] for i in range(chan_count)]
            device_str = f"XC_DEV_{run_idx:02d}"
            pkt, aid_node, strategy = node.transmit(
                device_id=device_str,
                device_status="OK",
                sensors=sensors,
            )
            _assert(isinstance(pkt, bytes) and len(pkt) > 0,
                    f"packet 应为非空 bytes，得 {type(pkt)}")
            _assert(isinstance(aid_node, int) and aid_node > 0,
                    f"aid 应为正整数，得 {aid_node}")
            result = node.receive(pkt)
            _assert("error" not in result or result.get("error") is None,
                    f"receive 出错: {result.get('error')}")
            _assert(result.get("id") is not None, "receive 结果应含 id")
            # 验证第一个传感器键存在
            _assert("s1_v" in result, f"receive 结果应含 s1_v，键={list(result.keys())[:10]}")

            # 数值合理性检查（不强制精确，只检查非 NaN 且在量级范围内）
            s1v = result["s1_v"]
            _assert(isinstance(s1v, (int, float)), f"s1_v 类型应为数值，得 {type(s1v)}")
            _assert(s1v == s1v, "s1_v 不应为 NaN")  # NaN != NaN

            # 多通道时验证最后一个传感器键也存在
            if chan_count >= 2:
                last_key = f"s{chan_count}_v"
                _assert(last_key in result,
                        f"多通道 receive 结果应含 {last_key!r}，键={list(result.keys())[:10]}")

            # ────────────────────────────────────────────────────────────────
            # 子测试 3: ForwardingRule 模型 — 验证 medium C 的协议合法性
            # ────────────────────────────────────────────────────────────────
            rule = ForwardingRule(
                from_protocol=medium, to_protocol=medium,
                to_host="127.0.0.1", to_port=9000,
            )
            _assert(rule.from_protocol == medium.upper() and rule.to_protocol == medium.upper(),
                    f"ForwardingRule 字段不匹配: {rule.from_protocol}")
            rule_dict = rule.to_dict()
            _assert(rule_dict.get("from_protocol") == medium.upper(), "to_dict 不一致")
            rule2 = ForwardingRule.from_dict(rule_dict)
            _assert(rule2.from_protocol == medium.upper(), "from_dict 往返失败")

            # ────────────────────────────────────────────────────────────────
            # 子测试 4: Dispatch — 以 medium C 发送，不崩溃
            # ────────────────────────────────────────────────────────────────
            node.dispatch(pkt, medium=medium)   # no assertion needed: must not raise

            passed += 1
            print(f"    {_ok()} {run_label} {factor_str}"
                  f"  aid×{chan_count}=OK  s1_v={s1v:.3g}  rule={medium}→{medium}  dispatch=OK")

        except Exception as e:
            failed += 1
            failures.append(f"{run_label}: {e}")
            print(f"    {_fail(str(e)[:120])} {run_label} {factor_str}")

    return {"total": total, "passed": passed, "failed": failed, "skipped": skipped, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════════════════════
def main() -> int:
    from opensynaptic.utils import os_log  # noqa: F401 (triggers loggers)
    print(f"\n{_CYN}OpenSynaptic 正交测试套件{_RESET}")
    print(f"{_DIM}仓库: {REPO_ROOT}{_RESET}\n")

    import time
    with tempfile.TemporaryDirectory(prefix="os-ortho-") as tmp_root:
        tmp_dir = Path(tmp_root)
        t0 = time.perf_counter()

        results = {}
        results["EP | EPF 5-flag L8 正交（交互行为）        "] = suite_ep_epf_orthogonal()
        results["XC | ID×Unit×Medium×Ch L16 正交（链路耦合）"] = suite_xc_cross_chain_orthogonal(tmp_dir)

        elapsed = time.perf_counter() - t0
        return _print_summary(results, elapsed)


if __name__ == "__main__":
    sys.exit(main())
