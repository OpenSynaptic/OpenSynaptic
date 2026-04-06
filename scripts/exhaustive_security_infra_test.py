#!/usr/bin/env python3
"""
OpenSynaptic 安全基础设施 & 随机ID 穷举测试
Exhaustive Security Infrastructure + Random ID Test

涵盖：
  A. IDAllocator — 随机 ID 分配、释放、租约、去重、并发
  B. OSHandshakeManager — 握手状态机：INIT→PLAINTEXT_SENT→DICT_READY→SECURE
  C. EnvironmentGuardService — 资源库、错误监听、状态写入
  D. EnhancedPortForwarder — 防火墙、流量整形、协议转换、中间件、生命周期
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
import threading
import time
from pathlib import Path

# ── 路径引导 ──────────────────────────────────────────────────────────────────
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

def _ok(msg=""):   return f"{_GRN}PASS{_RESET}" + (f"  {_DIM}{msg}{_RESET}" if msg else "")
def _fail(msg=""):  return f"{_RED}FAIL{_RESET}" + (f"  {msg}" if msg else "")
def _skip(msg=""):  return f"{_YLW}SKIP{_RESET}" + (f"  {_DIM}{msg}{_RESET}" if msg else "")
def _head(msg=""):  return f"\n{_CYN}{'─'*70}\n  {msg}\n{'─'*70}{_RESET}"

def _assert(cond, msg=""):
    if not cond:
        raise AssertionError(msg or "Assertion failed")

# ════════════════════════════════════════════════════════════════════════════
# 全局摘要打印
# ════════════════════════════════════════════════════════════════════════════
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
    rate = 100.0 * passed_t / (total_t - skipped_t) if (total_t - skipped_t) > 0 else 100.0
    print(f"  耗时: {elapsed*1000:.0f}ms   通过率: {rate:.1f}%")
    if all_failures:
        print(f"\n  失败详情 ({len(all_failures)} 条):")
        for f in all_failures:
            print(f"  {_RED}✗{_RESET} {f[:160]}")
    print()
    return 0 if failed_t == 0 else 1


# ════════════════════════════════════════════════════════════════════════════
# Suite A: IDAllocator 随机 ID 穷举
# ════════════════════════════════════════════════════════════════════════════
def suite_a_id_allocator(tmp_dir: Path) -> dict:
    total = passed = failed = skipped = 0
    failures: list[str] = []

    print(_head("Suite A: IDAllocator 随机 ID 分配 + 租约穷举"))

    try:
        from opensynaptic.utils.id_allocator import IDAllocator
    except ImportError as e:
        print(f"    {_skip(f'import failed: {e}')}")
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 1, "failures": []}

    persist = str(tmp_dir / "id_alloc_A.json")

    # ── A1: 基本分配与唯一性 ──────────────────────────────────────────────
    total += 1
    try:
        ida = IDAllocator(
            base_dir=str(tmp_dir), persist_file="id_alloc_A.json",
            start_id=1, end_id=9999,
            lease_policy={"offline_hold_days": 0, "min_lease_seconds": 0},
        )
        N = 200
        ids = [ida.allocate_id({"device_id": f"DEV{i:04d}"}) for i in range(N)]
        _assert(len(set(ids)) == N, f"重复 ID: {len(ids) - len(set(ids))} 个")
        _assert(all(1 <= x <= 9999 for x in ids), "ID 超出范围")
        passed += 1
        print(f"    {_ok()} A1  分配 {N} 个唯一 ID，范围 [1, 9999]")
    except Exception as e:
        failed += 1; failures.append(f"A1: {e}"); print(f"    {_fail(str(e))} A1")

    # ── A2: 随机大量 ID 分配 (1000个) ─────────────────────────────────────
    total += 1
    try:
        ida2 = IDAllocator(
            base_dir=str(tmp_dir), persist_file="id_alloc_A2.json",
            start_id=100, end_id=9999,
            lease_policy={"offline_hold_days": 0, "min_lease_seconds": 0},
        )
        rng = random.Random(42)
        n = 500
        ids2 = []
        for i in range(n):
            meta = {
                "device_id": f"RAND-{rng.randint(1, 9999):04d}",
                "serial": str(rng.randint(10000, 99999)),
            }
            ids2.append(ida2.allocate_id(meta))
        # 因为有设备去重，唯一 ID 数 < n；但数量合理
        unique = len(set(ids2))
        _assert(unique >= 1, "无唯一 ID")
        _assert(unique <= n, "唯一ID 超过请求数")
        passed += 1
        print(f"    {_ok()} A2  随机 {n} 次分配 → {unique} 个唯一 ID（去重后）")
    except Exception as e:
        failed += 1; failures.append(f"A2: {e}"); print(f"    {_fail(str(e))} A2")

    # ── A3: 设备去重 — 同设备键复用同一 ID ───────────────────────────────
    total += 1
    try:
        ida3 = IDAllocator(
            base_dir=str(tmp_dir), persist_file="id_alloc_A3.json",
            start_id=1, end_id=9999,
            lease_policy={"offline_hold_days": 1},
        )
        id_a = ida3.allocate_id({"device_id": "DEVICE_DEDUP_TEST"})
        id_b = ida3.allocate_id({"device_id": "DEVICE_DEDUP_TEST"})  # 同设备再分配
        _assert(id_a == id_b, f"去重失败: {id_a} != {id_b}")
        id_c = ida3.allocate_id({"device_id": "ANOTHER_DEVICE"})
        _assert(id_c != id_a, "不同设备应分配不同 ID")
        passed += 1
        print(f"    {_ok()} A3  设备去重: same_key→{id_a}=={id_b}, diff_key→{id_c}")
    except Exception as e:
        failed += 1; failures.append(f"A3: {e}"); print(f"    {_fail(str(e))} A3")

    # ── A4: release_id(immediate=True) 自动内部回收 + 重用 ──────────────
    # immediate=True 内部即调 _reclaim_expired_nolock，ID 立即回到池中；
    # 外部 reclaim_expired() 结果为 0（已被消耗）是预期行为。
    total += 1
    try:
        ida4 = IDAllocator(
            base_dir=str(tmp_dir), persist_file="id_alloc_A4.json",
            start_id=1, end_id=9999,
            lease_policy={"base_lease_seconds": 0, "min_lease_seconds": 0,
                          "offline_hold_days": 0},
        )
        id1 = ida4.allocate_id({"device_id": "D1"})
        ok = ida4.release_id(id1, immediate=True)
        _assert(ok, "release_id 应返回 True")
        # immediate=True 已在内部完成回收，is_allocated 应为 False
        _assert(not ida4.is_allocated(id1), f"立即释放后 {id1} 仍显示已分配")
        # 重用：下次分配应优先复用 id1（最小堆）
        id1_reuse = ida4.allocate_id({"device_id": "D_REUSE"})
        _assert(id1_reuse == id1, f"期望重用 id {id1}，得到 {id1_reuse}")
        passed += 1
        print(f"    {_ok()} A4  immediate release→内部自动回收→reuse: ID {id1} 被成功重用")
    except Exception as e:
        failed += 1; failures.append(f"A4: {e}"); print(f"    {_fail(str(e))} A4")

    # ── A5: allocate_pool ─────────────────────────────────────────────────
    total += 1
    try:
        ida5 = IDAllocator(
            base_dir=str(tmp_dir), persist_file="id_alloc_A5.json",
            start_id=1, end_id=9999,
            lease_policy={"offline_hold_days": 1},
        )
        pool = ida5.allocate_pool(50)
        _assert(len(pool) == 50, f"pool 应有 50 个，得 {len(pool)}")
        _assert(len(set(pool)) == 50, "pool 内有重复")
        passed += 1
        print(f"    {_ok()} A5  allocate_pool(50) → {pool[:3]}…{pool[-3:]}")
    except Exception as e:
        failed += 1; failures.append(f"A5: {e}"); print(f"    {_fail(str(e))} A5")

    # ── A6: release_pool ──────────────────────────────────────────────────
    total += 1
    try:
        count = ida5.release_pool(pool[:10], immediate=True)
        _assert(count == 10, f"release_pool 应返回 10，得 {count}")
        passed += 1
        print(f"    {_ok()} A6  release_pool(10) → {count} released")
    except Exception as e:
        failed += 1; failures.append(f"A6: {e}"); print(f"    {_fail(str(e))} A6")

    # ── A7: touch — 续约刷新 ─────────────────────────────────────────────
    total += 1
    try:
        ida7 = IDAllocator(
            base_dir=str(tmp_dir), persist_file="id_alloc_A7.json",
            start_id=1, end_id=9999,
            lease_policy={"offline_hold_days": 1},
        )
        aid = ida7.allocate_id({"device_id": "TOUCH_TEST"})
        before = ida7._allocated[aid]["lease_expires_at"]
        time.sleep(0.01)
        ok = ida7.touch(aid, meta={"device_id": "TOUCH_TEST", "extra": "v2"})
        _assert(ok, "touch 应返回 True")
        after = ida7._allocated[aid]["lease_expires_at"]
        _assert(after >= before, f"lease_expires_at 未刷新: {before} → {after}")
        passed += 1
        print(f"    {_ok()} A7  touch → lease_expires_at {before}→{after}")
    except Exception as e:
        failed += 1; failures.append(f"A7: {e}"); print(f"    {_fail(str(e))} A7")

    # ── A8: is_allocated / get_meta ───────────────────────────────────────
    total += 1
    try:
        _assert(ida7.is_allocated(aid), "is_allocated 应返回 True")
        meta = ida7.get_meta(aid)
        _assert(isinstance(meta, dict), "get_meta 应返回 dict")
        _assert(not ida7.is_allocated(99999), "未分配 ID 应返回 False")
        passed += 1
        print(f"    {_ok()} A8  is_allocated / get_meta 正常")
    except Exception as e:
        failed += 1; failures.append(f"A8: {e}"); print(f"    {_fail(str(e))} A8")

    # ── A9: stats() 结构 ──────────────────────────────────────────────────
    total += 1
    try:
        s = ida7.stats()
        for k in ("total_allocated", "total_released", "next_candidate", "range", "lease_policy", "lease_metrics"):
            _assert(k in s, f"stats 缺少 {k!r}")
        _assert(s["total_allocated"] >= 1)
        passed += 1
        print(f"    {_ok()} A9  stats() 结构完整: alloc={s['total_allocated']}, released={s['total_released']}")
    except Exception as e:
        failed += 1; failures.append(f"A9: {e}"); print(f"    {_fail(str(e))} A9")

    # ── A10: 并发安全 (20 线程同时分配) ──────────────────────────────────
    total += 1
    try:
        ida10 = IDAllocator(
            base_dir=str(tmp_dir), persist_file="id_alloc_A10.json",
            start_id=1, end_id=99999,
            lease_policy={"offline_hold_days": 1},
        )
        results_list = []
        errors_list = []
        def _worker(i):
            try:
                aid = ida10.allocate_id({"device_id": f"THREAD_{i}"})
                results_list.append(aid)
            except Exception as exc:
                errors_list.append(str(exc))
        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=5.0)
        _assert(not errors_list, f"并发异常: {errors_list}")
        _assert(len(set(results_list)) == len(results_list), "并发分配出现重复 ID")
        passed += 1
        print(f"    {_ok()} A10 20线程并发分配 → {len(results_list)} 个唯一 ID，0 冲突")
    except Exception as e:
        failed += 1; failures.append(f"A10: {e}"); print(f"    {_fail(str(e))} A10")

    # ── A11: 自适应租约速率（写入大量设备触发高速率模式）────────────────
    total += 1
    try:
        ida11 = IDAllocator(
            base_dir=str(tmp_dir), persist_file="id_alloc_A11.json",
            start_id=1, end_id=99999,
            lease_policy={
                "base_lease_seconds": 3600,
                "high_rate_threshold_per_hour": 1.0,  # 极低阈值，分配 2 个就触发
                "adaptive_enabled": True,
            },
        )
        # 连续分配触发速率自适应
        for i in range(5):
            ida11.allocate_id({"device_id": f"RATE_DEV_{i}"})
        s = ida11.stats()
        rate = s["lease_metrics"].get("new_device_rate_per_hour", 0)
        _assert(isinstance(rate, (int, float)), "rate 应为数值")
        passed += 1
        print(f"    {_ok()} A11 自适应速率计算: rate={rate:.2f}/h, eff_lease={s['lease_metrics'].get('effective_lease_seconds')}s")
    except Exception as e:
        failed += 1; failures.append(f"A11: {e}"); print(f"    {_fail(str(e))} A11")

    # ── A12: 持久化往返 — 重新加载后分配状态保留 ─────────────────────────
    total += 1
    try:
        ida12a = IDAllocator(
            base_dir=str(tmp_dir), persist_file="id_alloc_A12.json",
            start_id=1, end_id=9999,
            lease_policy={"offline_hold_days": 1},
        )
        saved_id = ida12a.allocate_id({"device_id": "PERSIST_TEST"})
        del ida12a  # 确保已保存
        # 重新从文件加载
        ida12b = IDAllocator(
            base_dir=str(tmp_dir), persist_file="id_alloc_A12.json",
            start_id=1, end_id=9999,
            lease_policy={"offline_hold_days": 1},
        )
        _assert(ida12b.is_allocated(saved_id), f"重载后 ID {saved_id} 应仍被分配")
        meta = ida12b.get_meta(saved_id)
        _assert(isinstance(meta, dict), "重载后 meta 应为 dict")
        # 同设备再次分配应复用
        reuse_id = ida12b.allocate_id({"device_id": "PERSIST_TEST"})
        _assert(reuse_id == saved_id, f"重载后设备去重失效: {reuse_id} != {saved_id}")
        passed += 1
        print(f"    {_ok()} A12 持久化往返: ID {saved_id} 重载后保留并去重成功")
    except Exception as e:
        failed += 1; failures.append(f"A12: {e}"); print(f"    {_fail(str(e))} A12")

    # ── A13: 池耗尽后 RuntimeError ───────────────────────────────────────
    total += 1
    try:
        ida13 = IDAllocator(
            base_dir=str(tmp_dir), persist_file="id_alloc_A13.json",
            start_id=1, end_id=3,   # 仅 3 个 ID
            lease_policy={"offline_hold_days": 365},
        )
        for i in range(3):
            ida13.allocate_id({"device_id": f"SMALL_{i}"})
        try:
            ida13.allocate_id({"device_id": "OVERFLOW"})
            failed += 1; failures.append("A13: 应抛出 RuntimeError 但未抛出")
            print(f"    {_fail('期望 RuntimeError 但未抛出')} A13")
        except RuntimeError:
            passed += 1
            print(f"    {_ok()} A13 池耗尽 → RuntimeError 正确抛出")
    except Exception as e:
        failed += 1; failures.append(f"A13: {e}"); print(f"    {_fail(str(e))} A13")

    return {"total": total, "passed": passed, "failed": failed, "skipped": skipped, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# Suite B: OSHandshakeManager 握手状态机
# ════════════════════════════════════════════════════════════════════════════
def suite_b_handshake(tmp_dir: Path) -> dict:
    total = passed = failed = skipped = 0
    failures: list[str] = []

    print(_head("Suite B: OSHandshakeManager 握手状态机穷举"))

    try:
        from opensynaptic.core.pycore.handshake import OSHandshakeManager, CMD
        from opensynaptic.utils import derive_session_key
    except ImportError as e:
        print(f"    {_skip(f'import failed: {e}')}")
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 1, "failures": []}

    secure_store = str(tmp_dir / "secure_sessions_B.json")
    reg_dir = str(tmp_dir / "registry_B")

    def _make_hm(**kwargs):
        return OSHandshakeManager(
            registry_dir=reg_dir,
            secure_store_path=secure_store,
            expire_seconds=3600,
            **kwargs,
        )

    # ── B1: 初始化 — INIT 状态 ──────────────────────────────────────────
    total += 1
    try:
        hm = _make_hm()
        _assert(hm.device_role == "duplex")
        _assert(not hm.has_secure_dict(42))
        _assert(not hm.should_encrypt_outbound(42))
        _assert(hm.get_session_key(42) is None)
        passed += 1
        print(f"    {_ok()} B1  初始化 INIT 状态正常")
    except Exception as e:
        failed += 1; failures.append(f"B1: {e}"); print(f"    {_fail(str(e))} B1")

    # ── B2: note_local_plaintext_sent → PLAINTEXT_SENT ──────────────────
    total += 1
    try:
        hm2 = _make_hm()
        ts = int(time.time())
        session = hm2.note_local_plaintext_sent(42, ts)
        _assert(session is not None, "session 不应为 None")
        _assert(session.get("state") == "PLAINTEXT_SENT")
        _assert(session.get("pending_key") is not None, "pending_key 应已派生")
        _assert(session.get("pending_timestamp") == ts)
        passed += 1
        print(f"    {_ok()} B2  note_local_plaintext_sent → state=PLAINTEXT_SENT, pending_key 派生")
    except Exception as e:
        failed += 1; failures.append(f"B2: {e}"); print(f"    {_fail(str(e))} B2")

    # ── B3: establish_remote_plaintext → DICT_READY ─────────────────────
    total += 1
    try:
        hm3 = _make_hm()
        ts = int(time.time())
        hm3.note_local_plaintext_sent(42, ts)
        session = hm3.establish_remote_plaintext(42, ts)
        _assert(session is not None)
        _assert(session.get("dict_ready"), "dict_ready 应为 True")
        _assert(session.get("state") == "DICT_READY")
        _assert(session.get("key") is not None, "key 应已设置")
        _assert(isinstance(session["key"], bytes), "key 应为 bytes")
        _assert(hm3.has_secure_dict(42), "has_secure_dict 应为 True")
        passed += 1
        print(f"    {_ok()} B3  establish_remote_plaintext → DICT_READY, key={session['key'].hex()[:16]}…")
    except Exception as e:
        failed += 1; failures.append(f"B3: {e}"); print(f"    {_fail(str(e))} B3")

    # ── B4: confirm_secure_dict → DICT_READY (pending_key 路径) ─────────
    total += 1
    try:
        hm4 = _make_hm()
        ts = int(time.time())
        hm4.note_local_plaintext_sent(42, ts)  # 生成 pending_key
        ok = hm4.confirm_secure_dict(42)
        _assert(ok, "confirm_secure_dict 应返回 True")
        _assert(hm4.has_secure_dict(42))
        key = hm4.get_session_key(42)
        _assert(isinstance(key, bytes))
        expected = derive_session_key(42, ts)
        _assert(key == expected, f"key 派生值不匹配: {key.hex()} != {expected.hex()}")
        passed += 1
        print(f"    {_ok()} B4  confirm_secure_dict 通过 pending_key 路径 → key 正确")
    except Exception as e:
        failed += 1; failures.append(f"B4: {e}"); print(f"    {_fail(str(e))} B4")

    # ── B5: mark_secure_channel → SECURE ────────────────────────────────
    total += 1
    try:
        hm5 = _make_hm()
        ts = int(time.time())
        hm5.note_local_plaintext_sent(42, ts)
        hm5.establish_remote_plaintext(42, ts)
        session = hm5.mark_secure_channel(42)
        _assert(session.get("state") == "SECURE")
        _assert(session.get("decrypt_confirmed"), "decrypt_confirmed 应为 True")
        _assert(hm5.should_encrypt_outbound(42), "should_encrypt_outbound 应为 True")
        passed += 1
        print(f"    {_ok()} B5  mark_secure_channel → state=SECURE, encrypt_outbound=True")
    except Exception as e:
        failed += 1; failures.append(f"B5: {e}"); print(f"    {_fail(str(e))} B5")

    # ── B6: 完整状态机路径（多个 AID） ──────────────────────────────────
    total += 1
    try:
        hm6 = _make_hm()
        ts = int(time.time())
        for aid in [1, 10, 255, 1000, 65535]:
            hm6.note_local_plaintext_sent(aid, ts + aid)
            s = hm6.establish_remote_plaintext(aid, ts + aid)
            _assert(s["state"] == "DICT_READY", f"aid={aid} 状态应为 DICT_READY")
            hm6.mark_secure_channel(aid)
            _assert(hm6.should_encrypt_outbound(aid), f"aid={aid} 应加密出站")
        passed += 1
        print(f"    {_ok()} B6  5 个不同 AID 均完成 INIT→SECURE 状态机跃迁")
    except Exception as e:
        failed += 1; failures.append(f"B6: {e}"); print(f"    {_fail(str(e))} B6")

    # ── B7: classify_and_dispatch — 空包 / 未知 CMD ──────────────────────
    total += 1
    try:
        hm7 = _make_hm()
        # 空包
        r = hm7.classify_and_dispatch(b"")
        _assert(r["type"] == "ERROR", f"空包应返回 ERROR，得 {r['type']}")
        # 未知 CMD 0xFF
        r2 = hm7.classify_and_dispatch(bytes([0xFF, 0x00, 0x00]))
        _assert(r2["type"] == "UNKNOWN", f"未知 CMD 应返回 UNKNOWN，得 {r2['type']}")
        passed += 1
        print(f"    {_ok()} B7  classify_and_dispatch 空包→ERROR, 0xFF→UNKNOWN")
    except Exception as e:
        failed += 1; failures.append(f"B7: {e}"); print(f"    {_fail(str(e))} B7")

    # ── B8: classify_and_dispatch — PING → CTRL ──────────────────────────
    total += 1
    try:
        hm8 = _make_hm()
        import struct
        # PING 包：cmd=9, seq=1
        ping_pkt = bytes([CMD.PING]) + struct.pack(">H", 1)
        r = hm8.classify_and_dispatch(ping_pkt)
        _assert(r["type"] == "CTRL", f"PING 应返回 CTRL，得 {r['type']}")
        _assert(r["cmd"] == CMD.PING)
        passed += 1
        print(f"    {_ok()} B8  PING → CTRL, response={r.get('response') and 'PONG' or 'None'}")
    except Exception as e:
        failed += 1; failures.append(f"B8: {e}"); print(f"    {_fail(str(e))} B8")

    # ── B9: tx_only 角色 — 入向 DATA 被忽略 ─────────────────────────────
    total += 1
    try:
        hm9 = _make_hm(device_role="tx_only")
        _assert(hm9.device_role == "tx_only")
        # DATA_FULL = 63 (0x3F)
        data_pkt = bytes([CMD.DATA_FULL, 0x00, 0x00, 0x00])
        r = hm9.classify_and_dispatch(data_pkt)
        _assert(r["type"] == "IGNORED", f"tx_only 中入向 DATA 应被忽略，得 {r['type']}")
        passed += 1
        print(f"    {_ok()} B9  tx_only 角色：入向 DATA 被 IGNORED")
    except Exception as e:
        failed += 1; failures.append(f"B9: {e}"); print(f"    {_fail(str(e))} B9")

    # ── B10: 持久化 — secure_sessions 写入与重载 ─────────────────────────
    total += 1
    try:
        hm10a = _make_hm()
        ts = int(time.time())
        hm10a.note_local_plaintext_sent(77, ts)
        hm10a.establish_remote_plaintext(77, ts)
        hm10a._save_secure_sessions(force=True)
        key_before = hm10a.get_session_key(77)
        # 重新实例化，从文件加载
        hm10b = _make_hm()
        key_after = hm10b.get_session_key(77)
        _assert(key_before is not None, "key_before 不应为 None")
        _assert(key_after is not None, "持久化重载后 key 不应为 None")
        _assert(key_before == key_after, "重载后 key 应与保存前一致")
        passed += 1
        print(f"    {_ok()} B10 secure_sessions 持久化往返: key={key_before.hex()[:16]}…")
    except Exception as e:
        failed += 1; failures.append(f"B10: {e}"); print(f"    {_fail(str(e))} B10")

    # ── B11: note_server_time ─────────────────────────────────────────────
    total += 1
    try:
        hm11 = _make_hm()
        hm11.note_server_time(0)
        _assert(hm11.last_server_time == 0, "ts=0 不应更新")
        hm11.note_server_time(1_700_000_000)
        _assert(hm11.last_server_time == 1_700_000_000)
        passed += 1
        print(f"    {_ok()} B11 note_server_time: ts=0 忽略, ts=1.7e9 接受")
    except Exception as e:
        failed += 1; failures.append(f"B11: {e}"); print(f"    {_fail(str(e))} B11")

    # ── B12: classify_and_dispatch — ID_REQUEST 需要 id_allocator ────────
    total += 1
    try:
        from opensynaptic.utils.id_allocator import IDAllocator
        import struct
        hm12 = _make_hm()
        hm12.id_allocator = IDAllocator(
            base_dir=str(tmp_dir), persist_file="id_alloc_B12.json",
            start_id=1, end_id=9999,
            lease_policy={"offline_hold_days": 1},
        )
        # ID_REQUEST 包：cmd=1, seq=0x0001, meta_len=0
        id_req = bytes([CMD.ID_REQUEST]) + struct.pack(">H", 1) + struct.pack(">H", 0)
        r = hm12.classify_and_dispatch(id_req, addr=("127.0.0.1", 9000))
        _assert(r["type"] == "CTRL", f"ID_REQUEST 应为 CTRL，得 {r['type']}")
        # 有 id_allocator 时应生成 ID_ASSIGN 响应
        _assert(r.get("response") is not None, "ID_REQUEST 应有响应包")
        _assert(r["response"][0] == CMD.ID_ASSIGN, f"响应应为 ID_ASSIGN，得 0x{r['response'][0]:02X}")
        passed += 1
        print(f"    {_ok()} B12 ID_REQUEST → ID_ASSIGN 响应正确")
    except Exception as e:
        failed += 1; failures.append(f"B12: {e}"); print(f"    {_fail(str(e))} B12")

    return {"total": total, "passed": passed, "failed": failed, "skipped": skipped, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# Suite C: EnvironmentGuardService
# ════════════════════════════════════════════════════════════════════════════
def suite_c_env_guard(tmp_dir: Path) -> dict:
    total = passed = failed = skipped = 0
    failures: list[str] = []

    print(_head("Suite C: EnvironmentGuardService 逻辑穷举"))

    try:
        from opensynaptic.services.env_guard.main import EnvironmentGuardService
        from opensynaptic.utils.errors import EnvironmentMissingError
    except ImportError as e:
        print(f"    {_skip(f'import failed: {e}')}")
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 1, "failures": []}

    eg_dir = tmp_dir / "env_guard_C"
    eg_dir.mkdir(parents=True, exist_ok=True)

    def _make_eg(**kw):
        cfg = {
            "enabled": True,
            "mode": "manual",
            "auto_start": False,
            "auto_install": False,
            "max_history": 50,
            "status_json_path": str(eg_dir / "status.json"),
            "resource_library_json_path": str(eg_dir / "resources.json"),
        }
        cfg.update(kw)
        return EnvironmentGuardService(node=None, **cfg)

    # ── C1: get_required_config 结构 ─────────────────────────────────────
    total += 1
    try:
        cfg = EnvironmentGuardService.get_required_config()
        for k in ("enabled", "mode", "auto_start", "auto_install", "max_history"):
            _assert(k in cfg, f"config 缺少 {k!r}")
        passed += 1
        print(f"    {_ok()} C1  get_required_config 结构完整")
    except Exception as e:
        failed += 1; failures.append(f"C1: {e}"); print(f"    {_fail(str(e))} C1")

    # ── C2: ensure_resource_library — 首次写入默认库 ─────────────────────
    total += 1
    try:
        eg = _make_eg()
        target = eg.ensure_resource_library(force_reset=True)
        _assert(target.exists(), "资源库文件应被创建")
        data = json.loads(target.read_text(encoding="utf-8"))
        _assert("resources" in data, "资源库应包含 resources")
        _assert(isinstance(data["resources"], dict))
        passed += 1
        print(f"    {_ok()} C2  ensure_resource_library → 文件已创建，结构合法")
    except Exception as e:
        failed += 1; failures.append(f"C2: {e}"); print(f"    {_fail(str(e))} C2")

    # ── C3: _on_error — 接收 EnvironmentMissingError 写入 issues ─────────
    total += 1
    try:
        eg3 = _make_eg()
        exc = EnvironmentMissingError("os_base62", missing_kind="native_library", resource="os_base62")
        event = {
            "error": exc,
            "payload": {"eid": "TEST_EID", "mid": "TEST_MID",
                        "category": "native", "error_type": "EnvironmentMissingError"},
        }
        eg3._on_error(event)
        _assert(len(eg3._issues) == 1, f"_issues 应有 1 条，得 {len(eg3._issues)}")
        issue = eg3._issues[0]
        _assert("environment" in issue, "issue 应含 environment")
        _assert("ts" in issue)
        passed += 1
        print(f"    {_ok()} C3  _on_error 写入 issues: {issue['error_type'] if 'error_type' in issue else 'OK'}")
    except Exception as e:
        failed += 1; failures.append(f"C3: {e}"); print(f"    {_fail(str(e))} C3")

    # ── C4: max_history 截断 ─────────────────────────────────────────────
    total += 1
    try:
        eg4 = _make_eg(max_history=5)
        ex = EnvironmentMissingError("X", missing_kind="native_library", resource="X")
        for i in range(10):
            eg4._on_error({"error": ex, "payload": {}})
        _assert(len(eg4._issues) == 5, f"issues 应被截断到 5，得 {len(eg4._issues)}")
        passed += 1
        print(f"    {_ok()} C4  max_history=5 截断正常: {len(eg4._issues)} issues")
    except Exception as e:
        failed += 1; failures.append(f"C4: {e}"); print(f"    {_fail(str(e))} C4")

    # ── C5: status_payload 结构 ─────────────────────────────────────────
    total += 1
    try:
        eg5 = _make_eg()
        payload = eg5._status_payload()
        for k in ("ok", "service", "issues_total", "attempts_total", "resource_summary"):
            _assert(k in payload, f"status_payload 缺少 {k!r}")
        _assert(payload["service"] == "env_guard")
        passed += 1
        print(f"    {_ok()} C5  _status_payload 结构合法: issues={payload['issues_total']}, attempts={payload['attempts_total']}")
    except Exception as e:
        failed += 1; failures.append(f"C5: {e}"); print(f"    {_fail(str(e))} C5")

    # ── C6: _write_status_json / _load_state_from_status_json 往返 ───────
    total += 1
    try:
        eg6 = _make_eg()
        ex = EnvironmentMissingError("Y", missing_kind="native_library", resource="Y")
        eg6._on_error({"error": ex, "payload": {"eid": "E6", "mid": "M6", "category": "nat", "error_type": "X"}})
        eg6._write_status_json()
        # 重新加载
        eg6b = _make_eg()
        eg6b._load_state_from_status_json()
        _assert(len(eg6b._issues) >= 1, f"重载后 issues 应 ≥ 1，得 {len(eg6b._issues)}")
        passed += 1
        print(f"    {_ok()} C6  status.json 往返: {len(eg6b._issues)} issues 重载成功")
    except Exception as e:
        failed += 1; failures.append(f"C6: {e}"); print(f"    {_fail(str(e))} C6")

    # ── C7: _resolve_resource_entry — 查找资源条目 ───────────────────────
    total += 1
    try:
        eg7 = _make_eg()
        eg7.ensure_resource_library(force_reset=True)
        entry = eg7._resolve_resource_entry("native_library", "os_base62")
        _assert(isinstance(entry, dict), f"应返回 dict，得 {type(entry)}")
        # 默认库定义了 native_library.os_base62
        _assert("commands" in entry or "urls" in entry, "entry 应含 commands 或 urls")
        # 不存在的资源类型 → 空 dict
        entry2 = eg7._resolve_resource_entry("nonexistent_kind", "x")
        _assert(isinstance(entry2, dict) and len(entry2) == 0, "未知种类应返回空 dict")
        passed += 1
        print(f"    {_ok()} C7  _resolve_resource_entry: native_library.os_base62 找到，未知种类→{{}}")
    except Exception as e:
        failed += 1; failures.append(f"C7: {e}"); print(f"    {_fail(str(e))} C7")

    # ── C8: auto_load + close 生命周期 ──────────────────────────────────
    total += 1
    try:
        eg8 = _make_eg(auto_start=False)
        eg8.auto_load()
        _assert(eg8._initialized, "auto_load 后 _initialized 应为 True")
        eg8.close()
        _assert(not eg8._initialized, "close 后 _initialized 应为 False")
        passed += 1
        print(f"    {_ok()} C8  auto_load + close 生命周期正常")
    except Exception as e:
        failed += 1; failures.append(f"C8: {e}"); print(f"    {_fail(str(e))} C8")

    return {"total": total, "passed": passed, "failed": failed, "skipped": skipped, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# Suite D: EnhancedPortForwarder 穷举
# ════════════════════════════════════════════════════════════════════════════
def suite_d_enhanced_forwarder(tmp_dir: Path) -> dict:
    total = passed = failed = skipped = 0
    failures: list[str] = []

    print(_head("Suite D: EnhancedPortForwarder 防火墙/整形/转换/中间件穷举"))

    try:
        from opensynaptic.services.port_forwarder.enhanced import (
            EnhancedPortForwarder, FirewallRule, TrafficShaper,
            ProtocolConverter, Middleware, ProxyRule,
        )
    except ImportError as e:
        print(f"    {_skip(f'import failed: {e}')}")
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 1, "failures": []}

    # ── D1: 初始化 + get_required_config ─────────────────────────────────
    total += 1
    try:
        cfg = EnhancedPortForwarder.get_required_config()
        for k in ("enabled", "firewall_enabled", "traffic_shaping_enabled",
                  "protocol_conversion_enabled", "middleware_enabled", "proxy_enabled"):
            _assert(k in cfg, f"config 缺少 {k!r}")
        epf = EnhancedPortForwarder(node=None)
        _assert(not epf.is_hijacked)
        _assert(len(epf.firewall_rules) == 0)
        passed += 1
        print(f"    {_ok()} D1  初始化 + get_required_config 结构合法")
    except Exception as e:
        failed += 1; failures.append(f"D1: {e}"); print(f"    {_fail(str(e))} D1")

    # ── D2: 功能开关 enable/disable/toggle ───────────────────────────────
    total += 1
    try:
        epf2 = EnhancedPortForwarder(node=None)
        for f in ("firewall", "traffic_shaping", "protocol_conversion", "middleware", "proxy"):
            ok = epf2.disable_feature(f)
            _assert(ok and not epf2.features_enabled[f], f"disable {f} 失败")
            ok = epf2.enable_feature(f)
            _assert(ok and epf2.features_enabled[f], f"enable {f} 失败")
            toggled = epf2.toggle_feature(f)
            _assert(toggled is False, f"toggle {f} 后应为 False")
            epf2.enable_feature(f)  # 恢复
        _assert(epf2.get_feature_status() == {k: True for k in epf2.features_enabled})
        passed += 1
        print(f"    {_ok()} D2  5 个功能开关 enable/disable/toggle 全部正常")
    except Exception as e:
        failed += 1; failures.append(f"D2: {e}"); print(f"    {_fail(str(e))} D2")

    # ── D3: 防火墙 — deny 规则阻断 ──────────────────────────────────────
    total += 1
    try:
        epf3 = EnhancedPortForwarder(node=None)
        deny_rule = FirewallRule(
            name="block_udp",
            action="deny",
            from_protocol="UDP",
            priority=10,
        )
        epf3.add_firewall_rule(deny_rule)
        pkt = b"\x3f\x00\x01\x02\x03"
        result = epf3.check_firewall(pkt, "UDP")
        _assert(result is False, f"UDP deny 规则应阻断，得 {result}")
        result_tcp = epf3.check_firewall(pkt, "TCP")
        _assert(result_tcp is True, f"TCP 无 deny 规则应放行，得 {result_tcp}")
        passed += 1
        print(f"    {_ok()} D3  防火墙 deny UDP → False, TCP → True")
    except Exception as e:
        failed += 1; failures.append(f"D3: {e}"); print(f"    {_fail(str(e))} D3")

    # ── D4: 防火墙 — allow 规则优先级 ───────────────────────────────────
    total += 1
    try:
        epf4 = EnhancedPortForwarder(node=None)
        # deny 所有，但 allow 高优先级覆盖
        epf4.add_firewall_rule(FirewallRule(name="deny_all", action="deny", priority=1))
        epf4.add_firewall_rule(FirewallRule(name="allow_udp", action="allow",
                                            from_protocol="UDP", priority=10))
        pkt = b"\x3f\x00\x01"
        _assert(epf4.check_firewall(pkt, "UDP") is True, "allow 高优先级应放行 UDP")
        _assert(epf4.check_firewall(pkt, "TCP") is False, "deny_all 低优先级应阻断 TCP")
        passed += 1
        print(f"    {_ok()} D4  防火墙优先级: allow(p=10)>deny(p=1) → UDP 放行, TCP 阻断")
    except Exception as e:
        failed += 1; failures.append(f"D4: {e}"); print(f"    {_fail(str(e))} D4")

    # ── D5: 流量整形 — 令牌桶 can_send ──────────────────────────────────
    total += 1
    try:
        epf5 = EnhancedPortForwarder(node=None)
        shaper = TrafficShaper(name="test_shaper", rate_limit_bps=1000, burst_capacity=500)
        epf5.add_traffic_shaper("udp_shaper", shaper)
        # 500 字节在突发容量内，应立即通过
        _assert(shaper.can_send(500), "500B ≤ burst_capacity=500 应允许")
        # 令牌已耗尽，再发 1 字节也不行
        _assert(not shaper.can_send(1), "令牌耗尽后 1B 应拒绝")
        wait = shaper.get_wait_time(100)
        _assert(wait > 0, f"耗尽后等待时间应 > 0，得 {wait}")
        passed += 1
        print(f"    {_ok()} D5  令牌桶: 500B 通过, 1B 拒绝, wait={wait:.3f}s")
    except Exception as e:
        failed += 1; failures.append(f"D5: {e}"); print(f"    {_fail(str(e))} D5")

    # ── D6: 流量整形 disabled 时不阻拦 ──────────────────────────────────
    total += 1
    try:
        epf6 = EnhancedPortForwarder(node=None, traffic_shaping_enabled=False)
        shaper6 = TrafficShaper(name="s6", rate_limit_bps=1, burst_capacity=0)
        epf6.add_traffic_shaper("s6", shaper6)
        wait = epf6.apply_traffic_shaping(b"x" * 9999, "s6")
        _assert(wait == 0.0, f"traffic_shaping disabled 应返回 0，得 {wait}")
        passed += 1
        print(f"    {_ok()} D6  traffic_shaping=False → apply 返回 0.0")
    except Exception as e:
        failed += 1; failures.append(f"D6: {e}"); print(f"    {_fail(str(e))} D6")

    # ── D7: 协议转换 — 自定义 transform_func ────────────────────────────
    total += 1
    try:
        epf7 = EnhancedPortForwarder(node=None)
        conv = ProtocolConverter(
            name="udp_to_tcp",
            from_protocol="UDP",
            to_protocol="TCP",
            transform_func=lambda pkt: pkt + b"\xDE\xAD",
        )
        epf7.add_protocol_converter(conv)
        original = b"\x01\x02\x03"
        converted = epf7.convert_protocol(original, "UDP", "TCP")
        _assert(converted == original + b"\xDE\xAD", f"转换结果不符: {converted!r}")
        # 不对应路由不转换
        not_conv = epf7.convert_protocol(original, "UART", "CAN")
        _assert(not_conv == original, "无匹配转换器应返回原包")
        passed += 1
        print(f"    {_ok()} D7  协议转换: UDP→TCP 追加 0xDEAD, UART→CAN 原包透传")
    except Exception as e:
        failed += 1; failures.append(f"D7: {e}"); print(f"    {_fail(str(e))} D7")

    # ── D8: 中间件 before/after 钩子 ────────────────────────────────────
    total += 1
    try:
        epf8 = EnhancedPortForwarder(node=None)
        log = []
        mw = Middleware(
            name="logger",
            before_dispatch=lambda pkt, medium: (log.append(("before", medium)) or pkt),
            after_dispatch=lambda pkt, medium, res: (log.append(("after", medium, res)) or res),
        )
        epf8.add_middleware(mw)
        pkt = b"\x01\x02\x03"
        pkt_out = epf8.execute_middlewares_before(pkt, "UDP")
        _assert(pkt_out == pkt, "before 钩子不应修改原包")
        res = epf8.execute_middlewares_after(pkt, "UDP", True)
        _assert(res is True, "after 钩子不应改变 result=True")
        _assert(log == [("before", "UDP"), ("after", "UDP", True)], f"日志顺序错误: {log}")
        passed += 1
        print(f"    {_ok()} D8  中间件 before/after 钩子执行顺序正确: {log}")
    except Exception as e:
        failed += 1; failures.append(f"D8: {e}"); print(f"    {_fail(str(e))} D8")

    # ── D9: auto_load + 完整生命周期（真实 dispatch mock） ───────────────
    total += 1
    try:
        import shutil as _shutil, json as _json
        from opensynaptic.core import OpenSynaptic

        with tempfile.TemporaryDirectory(prefix="os-epf-") as tmp2:
            cfg_src = REPO_ROOT / "Config.json"
            cfg_dst = Path(tmp2) / "Config.json"
            _shutil.copy2(cfg_src, cfg_dst)
            raw = _json.loads(cfg_dst.read_text("utf-8"))
            raw.setdefault("RESOURCES", {})["registry"] = str((Path(tmp2) / "reg").as_posix())
            sec = raw.setdefault("security_settings", {})
            sec["secure_session_store"] = str((Path(tmp2) / "ss.json").as_posix())
            sec.setdefault("id_lease", {})["persist_file"] = str((Path(tmp2) / "ida.json").as_posix())
            cfg_dst.write_text(_json.dumps(raw, indent=2, ensure_ascii=False), "utf-8")

            node = OpenSynaptic(config_path=str(cfg_dst))
            orig = node.dispatch

            epf9 = EnhancedPortForwarder(node=node)
            epf9.auto_load()
            _assert(epf9.is_hijacked, "auto_load 后应 hijacked")
            _assert(node.dispatch is not orig, "dispatch 应被替换")

            # 简单触发一次 dispatch（通过 node.transmit 生成包，再手动 dispatch）
            pkt, _, _ = node.transmit(
                device_id="DEVD9",
                device_status="OK",
                sensors=[["T1", "OK", 25.0, "Cel"]],
            )
            node.dispatch(pkt, medium="UDP")  # 通过 hijacked dispatch
            s = epf9.get_stats()
            _assert(s["total_packets"] >= 1, f"total_packets 应 ≥ 1，得 {s['total_packets']}")

            epf9.close()
            _assert(not epf9.is_hijacked)
        passed += 1
        print(f"    {_ok()} D9  EnhancedPortForwarder 完整生命周期，total_packets={s['total_packets']}")
    except Exception as e:
        failed += 1; failures.append(f"D9: {e}"); print(f"    {_fail(str(e))} D9")

    # ── D10: get_stats 结构 ──────────────────────────────────────────────
    total += 1
    try:
        epf10 = EnhancedPortForwarder(node=None)
        s = epf10.get_stats()
        for k in ("total_packets", "allowed_packets", "denied_packets",
                  "converted_packets", "middleware_executed", "features_enabled"):
            _assert(k in s, f"stats 缺少 {k!r}")
        passed += 1
        print(f"    {_ok()} D10 get_stats 结构完整")
    except Exception as e:
        failed += 1; failures.append(f"D10: {e}"); print(f"    {_fail(str(e))} D10")

    return {"total": total, "passed": passed, "failed": failed, "skipped": skipped, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════════════════════════
def main() -> int:
    from opensynaptic.utils import os_log
    print(f"\n{_CYN}OpenSynaptic 安全基础设施 + 随机ID 穷举测试{_RESET}")
    print(f"{_DIM}仓库: {REPO_ROOT}{_RESET}\n")

    with tempfile.TemporaryDirectory(prefix="os-sec-infra-") as tmp_root:
        tmp_dir = Path(tmp_root)
        t0 = __import__("time").perf_counter()

        results = {}
        results["A | IDAllocator 随机 ID 穷举      "] = suite_a_id_allocator(tmp_dir)
        results["B | OSHandshakeManager 状态机      "] = suite_b_handshake(tmp_dir)
        results["C | EnvironmentGuardService 逻辑   "] = suite_c_env_guard(tmp_dir)
        results["D | EnhancedPortForwarder 全组件   "] = suite_d_enhanced_forwarder(tmp_dir)

        elapsed = __import__("time").perf_counter() - t0
        return _print_summary(results, elapsed)


if __name__ == "__main__":
    sys.exit(main())
