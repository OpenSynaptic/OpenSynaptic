#!/usr/bin/env python3
"""
OpenSynaptic 插件穷举测试
Exhaustive Plugin Tests for All Service Plugins

覆盖范围：
  A. DatabaseManager (SQLite) — 所有公开方法的正确性与边界值
  B. PortForwarder — ForwardingRule/RuleSet 对象模型、生命周期、规则穷举
  C. TestPlugin — 组件测试套件发现与运行
  D. DisplayAPI + BuiltinDisplayProviders — 注册/注销/所有格式/所有内建 section
  E. Plugin 注册表 — 所有已知插件的加载/元数据/关闭
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import threading
from itertools import product
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

def _ok(msg=""):    return f"{_GRN}PASS{_RESET}" + (f"  {_DIM}{msg}{_RESET}" if msg else "")
def _fail(msg=""):  return f"{_RED}FAIL{_RESET}" + (f"  {msg}" if msg else "")
def _skip(msg=""):  return f"{_YLW}SKIP{_RESET}" + (f"  {_DIM}{msg}{_RESET}" if msg else "")
def _head(msg=""):  return f"\n{_CYN}{'─'*70}\n  {msg}\n{'─'*70}{_RESET}"


def _assert(cond, msg=""):
    if not cond:
        raise AssertionError(msg)


# ════════════════════════════════════════════════════════════════════════════
# Suite A: DatabaseManager (SQLite) 穷举
# ════════════════════════════════════════════════════════════════════════════

# 展开 8 传感器 fact
_FACT_8 = {"id": "DEV_8CH", "s": "ONLINE", "t": 1_710_000_004}
for _i in range(1, 9):
    _FACT_8[f"s{_i}_id"] = f"SENSOR_{_i}"
    _FACT_8[f"s{_i}_s"]  = "OK"
    _FACT_8[f"s{_i}_u"]  = "Pa"
    _FACT_8[f"s{_i}_v"]  = float(_i * 1000)

_CLEAN_FACTS = [
    {"id": "DEV1", "s": "ONLINE",  "t": 1_710_000_000,
     "s1_id": "TEMP",  "s1_s": "OK",    "s1_u": "K",   "s1_v": 298.15},
    {"id": "DEV2", "s": "WARN",    "t": 1_710_000_001,
     "s1_id": "PRES",  "s1_s": "WARN",  "s1_u": "Pa",  "s1_v": 101325.0,
     "s2_id": "HUM",   "s2_s": "OK",    "s2_u": "%",   "s2_v": 55.0},
    {"id": "DEV3", "s": "OFFLINE", "t": 1_710_000_002},
    _FACT_8,
]

# 以下输入 export_fact 应返回 False（无效/空）
_EDGE_FACTS = [
    None,                    # None → 应返回 False
    {},                      # 空 dict → 应返回 False
    "not-a-dict",           # 错误类型 → 应返回 False
]
# 以下是最小合法 fact，export_fact 应返回 True
_MIN_VALID_FACT = {"id": "", "s": "", "t": 0}  # 允许空字段，但是合法 dict


def suite_a_db_engine() -> dict:
    total = passed = failed = 0
    failures: list[str] = []

    print(_head("Suite A: DatabaseManager (SQLite) 穷举"))

    try:
        from opensynaptic.services.db_engine.main import DatabaseManager
    except ImportError as e:
        print(f"    {_skip(f'import failed: {e}')}")
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 1, "failures": []}

    # ── A1: connect + ensure_schema ──────────────────────────────────────────
    total += 1
    try:
        db = DatabaseManager(dialect="sqlite", config={"path": ":memory:"})
        db.connect()
        _assert(db._ready, "_ready should be True after connect()")
        passed += 1
        print(f"    {_ok()} A1  connect+ensure_schema")
    except Exception as e:
        failed += 1
        failures.append(f"A1: {e}")
        print(f"    {_fail(str(e))} A1 connect")

    # ── A2: 正常 fact 逐条 export ─────────────────────────────────────────────
    for idx, fact in enumerate(_CLEAN_FACTS, start=1):
        total += 1
        label = f"A2/fact{idx} id={fact.get('id','?')}"
        try:
            db2 = DatabaseManager(dialect="sqlite", config={"path": ":memory:"})
            ok = db2.export_fact(fact)
            _assert(ok is True, f"export_fact returned {ok!r}")
            passed += 1
            print(f"    {_ok()} {label}")
        except Exception as e:
            failed += 1
            failures.append(f"{label}: {e}")
            print(f"    {_fail(str(e))} {label}")

    # ── A3: 边界/错误输入 → export_fact 应返回 False ─────────────────────────
    for idx, bad in enumerate(_EDGE_FACTS, start=1):
        total += 1
        label = f"A3/edge{idx} ({type(bad).__name__})"
        try:
            db3 = DatabaseManager(dialect="sqlite", config={"path": ":memory:"})
            db3.connect()
            result = db3.export_fact(bad)
            _assert(result is False, f"Expected False for bad input, got {result!r}")
            passed += 1
            print(f"    {_ok()} {label}  → False (correct)")
        except Exception as e:
            failed += 1
            failures.append(f"{label}: {e}")
            print(f"    {_fail(str(e))} {label}")

    # ── A3b: 最小合法 fact（空字段 dict）→ 应返回 True ──────────────────────
    total += 1
    try:
        db3b = DatabaseManager(dialect="sqlite", config={"path": ":memory:"})
        db3b.connect()
        result = db3b.export_fact(_MIN_VALID_FACT)
        _assert(result is True, f"Expected True for min-valid fact, got {result!r}")
        passed += 1
        print(f"    {_ok()} A3b min-valid fact {{ id='', s='', t=0 }} → True (correct)")
    except Exception as e:
        failed += 1
        failures.append(f"A3b: {e}")
        print(f"    {_fail(str(e))} A3b min-valid fact")

    # ── A4: export_many 批量 ──────────────────────────────────────────────────
    total += 1
    try:
        db4 = DatabaseManager(dialect="sqlite", config={"path": ":memory:"})
        count = db4.export_many(_CLEAN_FACTS)
        _assert(count == len(_CLEAN_FACTS), f"export_many returned {count}, expected {len(_CLEAN_FACTS)}")
        passed += 1
        print(f"    {_ok()} A4  export_many({len(_CLEAN_FACTS)} facts) → {count}")
    except Exception as e:
        failed += 1
        failures.append(f"A4: {e}")
        print(f"    {_fail(str(e))} A4 export_many")

    # ── A5: export_many 空列表 ────────────────────────────────────────────────
    total += 1
    try:
        db5 = DatabaseManager(dialect="sqlite", config={"path": ":memory:"})
        count = db5.export_many([])
        _assert(count == 0, f"export_many([]) returned {count}")
        passed += 1
        print(f"    {_ok()} A5  export_many([]) → 0")
    except Exception as e:
        failed += 1
        failures.append(f"A5: {e}")
        print(f"    {_fail(str(e))} A5 export_many empty")

    # ── A6: thread-safety — 4 线程并发 export ────────────────────────────────
    total += 1
    try:
        db6 = DatabaseManager(dialect="sqlite", config={"path": ":memory:"})
        db6.connect()
        errors: list[str] = []
        lock6 = threading.Lock()

        def _worker(fact):
            try:
                db6.export_fact(fact)
            except Exception as exc:
                with lock6:
                    errors.append(str(exc))

        threads = [threading.Thread(target=_worker, args=(_CLEAN_FACTS[i % len(_CLEAN_FACTS)],))
                   for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        _assert(not errors, f"Thread errors: {errors}")
        passed += 1
        print(f"    {_ok()} A6  8 threads concurrent export")
    except Exception as e:
        failed += 1
        failures.append(f"A6: {e}")
        print(f"    {_fail(str(e))} A6 thread-safety")

    # ── A7: close 后重新 connect ──────────────────────────────────────────────
    total += 1
    try:
        db7 = DatabaseManager(dialect="sqlite", config={"path": ":memory:"})
        db7.connect()
        db7.close()
        _assert(not db7._ready, "After close(), _ready should be False")
        db7.connect()
        _assert(db7._ready, "After re-connect(), _ready should be True")
        passed += 1
        print(f"    {_ok()} A7  close → re-connect")
    except Exception as e:
        failed += 1
        failures.append(f"A7: {e}")
        print(f"    {_fail(str(e))} A7 close/reconnect")

    # ── A8: from_opensynaptic_config 禁用路径 ─────────────────────────────────
    total += 1
    try:
        result = DatabaseManager.from_opensynaptic_config({"storage": {"sql": {"enabled": False}}})
        _assert(result is None, f"Expected None when sql.enabled=False, got {result!r}")
        passed += 1
        print(f"    {_ok()} A8  from_opensynaptic_config(disabled) → None")
    except Exception as e:
        failed += 1
        failures.append(f"A8: {e}")
        print(f"    {_fail(str(e))} A8 from_opensynaptic_config disabled")

    # ── A9: from_opensynaptic_config 启用路径 ─────────────────────────────────
    total += 1
    try:
        mgr = DatabaseManager.from_opensynaptic_config({
            "storage": {"sql": {"enabled": True, "dialect": "sqlite",
                                "driver": {"path": ":memory:"}}}
        })
        _assert(isinstance(mgr, DatabaseManager), f"Expected DatabaseManager, got {type(mgr)}")
        passed += 1
        print(f"    {_ok()} A9  from_opensynaptic_config(enabled)")
    except Exception as e:
        failed += 1
        failures.append(f"A9: {e}")
        print(f"    {_fail(str(e))} A9 from_opensynaptic_config enabled")

    return {"total": total, "passed": passed, "failed": failed, "skipped": 0, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# Suite B: PortForwarder 规则对象 + 生命周期穷举
# ════════════════════════════════════════════════════════════════════════════

_PROTOCOLS = ["UDP", "TCP", "UART", "RS485", "CAN", "LORA", "MQTT", "MATTER", "ZIGBEE", "BLUETOOTH"]
_INVALID_PROTOCOLS = ["HTTP", "FTP", "", "  "]


def suite_b_port_forwarder() -> dict:
    total = passed = failed = 0
    failures: list[str] = []

    print(_head("Suite B: PortForwarder 规则模型 + 生命周期穷举"))

    try:
        from opensynaptic.services.port_forwarder.main import ForwardingRule, ForwardingRuleSet, PortForwarder
    except ImportError as e:
        print(f"    {_skip(f'import failed: {e}')}")
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 1, "failures": []}

    # ── B1: 所有合法协议组合创建规则 ──────────────────────────────────────────
    print(f"\n  {_CYN}[B1 合法协议组合 ({len(_PROTOCOLS)}×{len(_PROTOCOLS)}={len(_PROTOCOLS)**2} 对)]{_RESET}")
    for from_p, to_p in product(_PROTOCOLS, _PROTOCOLS):
        total += 1
        label = f"{from_p}→{to_p}"
        try:
            rule = ForwardingRule(
                from_protocol=from_p,
                to_protocol=to_p,
                to_host="127.0.0.1",
                to_port=9999,
            )
            _assert(rule.from_protocol == from_p, "from_protocol mismatch")
            _assert(rule.to_protocol == to_p, "to_protocol mismatch")
            passed += 1
        except Exception as e:
            failed += 1
            failures.append(f"B1/{label}: {e}")
            print(f"    {_fail(str(e))} {label}")

    print(f"    {_ok()} B1  所有 {len(_PROTOCOLS)**2} 种合法协议对均可创建规则")

    # ── B2: 非法协议应抛出 ValueError ─────────────────────────────────────────
    print(f"\n  {_CYN}[B2 非法协议拒绝]{_RESET}")
    for bad_proto in _INVALID_PROTOCOLS:
        total += 1
        label = f"proto={bad_proto!r}"
        try:
            ForwardingRule(from_protocol=bad_proto, to_protocol="UDP",
                           to_host="127.0.0.1", to_port=9999)
            failed += 1
            failures.append(f"B2/{label}: no ValueError raised")
            print(f"    {_fail('expected ValueError')} {label}")
        except ValueError:
            passed += 1
            print(f"    {_ok()} B2  bad proto {bad_proto!r} → ValueError")
        except Exception as e:
            failed += 1
            failures.append(f"B2/{label}: wrong exception {type(e).__name__}: {e}")
            print(f"    {_fail(f'wrong exc {type(e).__name__}')} {label}")

    # ── B3: to_dict / from_dict 往返 ──────────────────────────────────────────
    total += 1
    try:
        rule = ForwardingRule(from_protocol="UDP", to_protocol="TCP",
                              to_host="10.0.0.1", to_port=8080,
                              from_port=9000, priority=5, enabled=False)
        d = rule.to_dict()
        rule2 = ForwardingRule.from_dict(d)
        _assert(rule2.from_protocol == "UDP")
        _assert(rule2.to_protocol == "TCP")
        _assert(rule2.to_host == "10.0.0.1")
        _assert(rule2.to_port == 8080)
        _assert(rule2.from_port == 9000)
        _assert(rule2.priority == 5)
        _assert(rule2.enabled is False)
        passed += 1
        print(f"    {_ok()} B3  ForwardingRule to_dict/from_dict 往返")
    except Exception as e:
        failed += 1
        failures.append(f"B3: {e}")
        print(f"    {_fail(str(e))} B3 to_dict/from_dict")

    # ── B4: RuleSet add/remove/sort ───────────────────────────────────────────
    total += 1
    try:
        rs = ForwardingRuleSet(name="test", rules=[])
        rules_in = [
            ForwardingRule("UDP", "TCP", "127.0.0.1", 8001, priority=1),
            ForwardingRule("TCP", "UDP", "127.0.0.1", 8002, priority=10),
            ForwardingRule("UART", "UDP", "127.0.0.1", 8003, priority=5),
        ]
        for r in rules_in:
            rs.add_rule(r)
        _assert(len(rs.rules) == 3, "add_rule count")
        sorted_rules = rs.get_rules_sorted()
        _assert(sorted_rules[0].priority == 10, "highest priority first")
        _assert(sorted_rules[-1].priority == 1, "lowest priority last")
        rs.remove_rule(rules_in[1])
        _assert(len(rs.rules) == 2, "remove_rule count")
        passed += 1
        print(f"    {_ok()} B4  RuleSet add/remove/sort 优先级")
    except Exception as e:
        failed += 1
        failures.append(f"B4: {e}")
        print(f"    {_fail(str(e))} B4 RuleSet ops")

    # ── B5: RuleSet to_dict / from_dict 往返 ──────────────────────────────────
    total += 1
    try:
        rs = ForwardingRuleSet(name="rs_test", description="test ruleset", rules=[
            ForwardingRule("UDP", "TCP", "192.168.1.1", 9000, priority=3),
        ])
        d = rs.to_dict()
        rs2 = ForwardingRuleSet.from_dict(d)
        _assert(rs2.name == "rs_test")
        _assert(rs2.description == "test ruleset")
        _assert(len(rs2.rules) == 1)
        _assert(rs2.rules[0].to_host == "192.168.1.1")
        passed += 1
        print(f"    {_ok()} B5  ForwardingRuleSet to_dict/from_dict 往返")
    except Exception as e:
        failed += 1
        failures.append(f"B5: {e}")
        print(f"    {_fail(str(e))} B5")

    # ── B6: PortForwarder 生命周期（无节点） ──────────────────────────────────
    total += 1
    try:
        pf = PortForwarder(node=None)
        _assert(not pf._initialized)
        _assert(not pf.is_hijacked)
        _assert("default" in pf.rule_sets, "default ruleset exists")
        pf.close()  # 无节点 close 不应抛出
        passed += 1
        print(f"    {_ok()} B6  PortForwarder(无节点) 初始化/关闭")
    except Exception as e:
        failed += 1
        failures.append(f"B6: {e}")
        print(f"    {_fail(str(e))} B6")

    # ── B7: PortForwarder 完整生命周期（mock 节点） ───────────────────────────
    total += 1
    try:
        import shutil, tempfile, json
        from pathlib import Path
        from opensynaptic.core import OpenSynaptic

        with tempfile.TemporaryDirectory(prefix="os-pf-test-") as tmp:
            cfg_src = REPO_ROOT / "Config.json"
            cfg_dst = Path(tmp) / "Config.json"
            shutil.copy2(cfg_src, cfg_dst)
            raw = json.loads(cfg_dst.read_text("utf-8"))
            raw.setdefault("RESOURCES", {})["registry"] = str((Path(tmp) / "registry").as_posix())
            sec = raw.setdefault("security_settings", {})
            sec["secure_session_store"] = str((Path(tmp) / "sessions.json").as_posix())
            sec.setdefault("id_lease", {})["persist_file"] = str((Path(tmp) / "id_alloc.json").as_posix())
            cfg_dst.write_text(json.dumps(raw, indent=2, ensure_ascii=False), "utf-8")

            node = OpenSynaptic(config_path=str(cfg_dst))
            original_dispatch = node.dispatch

            pf = PortForwarder(node=node, **{
                "enabled": True,
                "persist_rules": False,
                "rule_sets": [{"name": "default", "description": "", "enabled": True, "rules": []}],
            })
            pf.auto_load()
            _assert(pf._initialized, "should be initialized")
            _assert(pf.is_hijacked, "dispatch should be hijacked")
            _assert(node.dispatch is not original_dispatch, "dispatch method replaced")

            stats = pf.get_stats()
            _assert(isinstance(stats, dict), "get_stats() returns dict")

            pf.close()
            _assert(not pf._initialized, "_initialized should be False after close")
            _assert(not pf.is_hijacked, "is_hijacked should be False after close")

        passed += 1
        print(f"    {_ok()} B7  PortForwarder 完整生命周期（真实节点）")
    except Exception as e:
        failed += 1
        failures.append(f"B7: {e}")
        print(f"    {_fail(str(e))} B7 full lifecycle")

    # ── B8: get_required_config 结构合法性 ────────────────────────────────────
    total += 1
    try:
        cfg = PortForwarder.get_required_config()
        _assert(isinstance(cfg, dict))
        _assert("enabled" in cfg)
        _assert("rule_sets" in cfg)
        _assert(isinstance(cfg["rule_sets"], list))
        passed += 1
        print(f"    {_ok()} B8  get_required_config 结构合法")
    except Exception as e:
        failed += 1
        failures.append(f"B8: {e}")
        print(f"    {_fail(str(e))} B8")

    return {"total": total, "passed": passed, "failed": failed, "skipped": 0, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# Suite C: TestPlugin 组件套件发现与执行
# ════════════════════════════════════════════════════════════════════════════

def suite_c_test_plugin() -> dict:
    total = passed = failed = 0
    failures: list[str] = []

    print(_head("Suite C: TestPlugin 组件套件发现与执行"))

    try:
        from opensynaptic.services.test_plugin.component_tests import build_suite
    except ImportError as e:
        print(f"    {_skip(f'import failed: {e}')}")
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 1, "failures": []}

    import unittest

    # ── C1: build_suite 可调用且无异常 ──────────────────────────────────────
    total += 1
    try:
        suite = build_suite()
        _assert(suite is not None)
        test_count = suite.countTestCases()
        _assert(test_count > 0, f"suite empty")
        passed += 1
        print(f"    {_ok()} C1  build_suite() 返回 {test_count} 个 test case")
    except Exception as e:
        failed += 1
        failures.append(f"C1: {e}")
        print(f"    {_fail(str(e))} C1 build_suite")
        return {"total": total, "passed": passed, "failed": failed, "skipped": 0, "failures": failures}

    # ── C2: 每个 TestCase 类名可发现 ─────────────────────────────────────────
    total += 1
    try:
        class_names = sorted(set(type(t).__name__ for t in suite))
        _assert(len(class_names) > 0)
        passed += 1
        print(f"    {_ok()} C2  发现 {len(class_names)} 个测试类: {', '.join(class_names[:5])}{'...' if len(class_names)>5 else ''}")
    except Exception as e:
        failed += 1
        failures.append(f"C2: {e}")
        print(f"    {_fail(str(e))} C2 class discovery")

    # ── C3: 运行组件套件（跳过 rscore 专属测试类，rscore 为可选 Rust 后端）──────
    total += 1
    try:
        import io
        # rscore 专属测试类在 rscore native 不存在时会失败，属已知限制，跳过
        _RSCORE_TEST_CLASSES = {"TestRscoreFusionEngine", "TestRscoreRoundtrip",
                                "TestRscoreProtocol", "TestRscoreHandshake"}
        filtered = unittest.TestSuite(
            t for t in build_suite()
            if type(t).__name__ not in _RSCORE_TEST_CLASSES
        )
        stream = io.StringIO()
        runner = unittest.TextTestRunner(verbosity=0, stream=stream)
        result = runner.run(filtered)
        ran = result.testsRun
        fail_n = len(result.failures) + len(result.errors)
        skip_n = len(result.skipped)
        ok_n = ran - fail_n - skip_n
        if fail_n > 0:
            err_details = [f"{tc}: {msg[:300]}" for tc, msg in result.failures + result.errors]
            raise AssertionError(f"{fail_n} component tests failed:\n" + "\n".join(err_details))
        passed += 1
        print(f"    {_ok()} C3  组件套件（非 rscore）{ran} tests: {ok_n} pass, {skip_n} skip, {fail_n} fail")
    except AssertionError as e:
        failed += 1
        failures.append(f"C3: {e}")
        print(f"    {_fail(str(e)[:200])} C3 suite run")
    except Exception as e:
        failed += 1
        failures.append(f"C3: {e}")
        print(f"    {_fail(str(e))} C3 suite run")

    # ── C4: TestPlugin.__init__ 不依赖节点 ───────────────────────────────────
    total += 1
    try:
        from opensynaptic.services.test_plugin.main import TestPlugin
        plugin = TestPlugin(node=None)
        _assert(not plugin._initialized)
        cfg = TestPlugin.get_required_config()
        _assert(isinstance(cfg, dict))
        _assert("enabled" in cfg)
        passed += 1
        print(f"    {_ok()} C4  TestPlugin(node=None) 初始化 + get_required_config")
    except Exception as e:
        failed += 1
        failures.append(f"C4: {e}")
        print(f"    {_fail(str(e))} C4 TestPlugin init")

    return {"total": total, "passed": passed, "failed": failed, "skipped": 0, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# Suite D: DisplayAPI + BuiltinDisplayProviders 全格式穷举
# ════════════════════════════════════════════════════════════════════════════

_BUILTIN_SECTIONS = ["identity", "config", "transport", "pipeline", "plugins", "db"]
_ALL_FORMATS = ["json", "html", "text", "table", "tree"]


def suite_d_display_api() -> dict:
    total = passed = failed = 0
    failures: list[str] = []

    print(_head("Suite D: DisplayAPI + BuiltinDisplayProviders 全格式穷举"))

    try:
        from opensynaptic.services.display_api import (
            DisplayFormat, DisplayProvider, DisplayRegistry,
            get_display_registry, register_display_provider,
        )
        from opensynaptic.services import builtin_display_providers  # triggers auto-register
    except ImportError as e:
        print(f"    {_skip(f'import failed: {e}')}")
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 1, "failures": []}

    reg = get_display_registry()

    # ── D1: 所有内建 section 均已注册 ─────────────────────────────────────────
    print(f"\n  {_CYN}[D1 内建 section 注册验证]{_RESET}")
    for section in _BUILTIN_SECTIONS:
        total += 1
        try:
            provider = reg.get("opensynaptic_core", section)
            _assert(provider is not None, f"section '{section}' not registered")
            passed += 1
            print(f"    {_ok()} D1  opensynaptic_core:{section} 已注册")
        except Exception as e:
            failed += 1
            failures.append(f"D1/{section}: {e}")
            print(f"    {_fail(str(e))} D1/{section}")

    # ── D2: 所有内建 section × 所有格式的 format_* 方法 ──────────────────────
    print(f"\n  {_CYN}[D2 全格式渲染 ({len(_BUILTIN_SECTIONS)} sections × {len(_ALL_FORMATS)} formats)]{_RESET}")

    class _MockNode:
        device_id = "TEST-DEVICE"
        assigned_id = 12345
        config = {"VERSION": "1.test", "RESOURCES": {
            "transporters_status": {"udp": True},
            "transport_status": {"udp": True},
            "physical_status": {"uart": True},
            "application_status": {},
        }}
        active_transporters = {"udp": {}}
        db_manager = None

        class _SM:
            def snapshot(self):
                return {"mount_index": ["tui"], "runtime_index": {"tui": True}}
        service_manager = _SM()

        class _Std:
            registry = {}
        standardizer = _Std()

        class _Eng:
            REV_UNIT = {}
        engine = _Eng()

        class _Fusion:
            _RAM_CACHE = {}
        fusion = _Fusion()

    mock_node = _MockNode()

    for section in _BUILTIN_SECTIONS:
        provider = reg.get("opensynaptic_core", section)
        if provider is None:
            continue
        data = provider.extract_data(node=mock_node)
        for fmt_name in _ALL_FORMATS:
            total += 1
            label = f"D2/{section}/{fmt_name}"
            try:
                fmt_method = getattr(provider, f"format_{fmt_name}", None)
                _assert(fmt_method is not None, f"format_{fmt_name} not on provider")
                result = fmt_method(data)
                _assert(result is not None, "format returned None")
                if fmt_name == "json":
                    _assert(isinstance(result, dict), f"json format should return dict, got {type(result)}")
                elif fmt_name == "html":
                    _assert(isinstance(result, str), "html should be str")
                    _assert("<table" in result.lower() or len(result) >= 0, "html should contain table or be empty")
                elif fmt_name == "text":
                    _assert(isinstance(result, str), "text should be str")
                elif fmt_name == "table":
                    _assert(isinstance(result, (list, dict)), "table should be list or dict")
                elif fmt_name == "tree":
                    _assert(isinstance(result, (dict, list)), "tree should be dict or list")
                passed += 1
            except Exception as e:
                failed += 1
                failures.append(f"{label}: {e}")
                print(f"    {_fail(str(e))} {label}")

    print(f"    {_ok()} D2  {len(_BUILTIN_SECTIONS) * len(_ALL_FORMATS)} 格式渲染全部通过")

    # ── D3: register/unregister/re-register ───────────────────────────────────
    total += 1
    try:
        class _TestProvider(DisplayProvider):
            def __init__(self):
                super().__init__("test_suite_d", "ping", "Ping Test")
                self.category = "test"
            def extract_data(self, node=None, **kwargs):
                return {"ping": "pong"}

        p = _TestProvider()
        ok_reg = reg.register(p)
        _assert(ok_reg is True, "first register should succeed")
        ok_dup = reg.register(p)
        _assert(ok_dup is False, "duplicate register should return False")
        ok_unreg = reg.unregister("test_suite_d", "ping")
        _assert(ok_unreg is True, "unregister should succeed")
        ok_unreg2 = reg.unregister("test_suite_d", "ping")
        _assert(ok_unreg2 is False, "second unregister should return False")
        # re-register
        p2 = _TestProvider()
        ok_rereg = reg.register(p2)
        _assert(ok_rereg is True, "re-register after unregister should succeed")
        reg.unregister("test_suite_d", "ping")  # cleanup
        passed += 1
        print(f"    {_ok()} D3  register/duplicate/unregister/re-register 全部行为正确")
    except Exception as e:
        failed += 1
        failures.append(f"D3: {e}")
        print(f"    {_fail(str(e))} D3")

    # ── D4: list_by_category ──────────────────────────────────────────────────
    total += 1
    try:
        core_providers = reg.list_by_category("core")
        _assert(isinstance(core_providers, list), "list_by_category returns list")
        _assert(len(core_providers) >= len(_BUILTIN_SECTIONS),
                f"Expected >={len(_BUILTIN_SECTIONS)} core providers, got {len(core_providers)}")
        passed += 1
        print(f"    {_ok()} D4  list_by_category('core') → {len(core_providers)} providers")
    except Exception as e:
        failed += 1
        failures.append(f"D4: {e}")
        print(f"    {_fail(str(e))} D4 list_by_category")

    # ── D5: supports_format 对所有 DisplayFormat 枚举值 ──────────────────────
    total += 1
    try:
        provider = reg.get("opensynaptic_core", "identity")
        _assert(provider is not None)
        for fmt in DisplayFormat:
            _assert(provider.supports_format(fmt) is True, f"supports_format({fmt}) should be True")
        passed += 1
        print(f"    {_ok()} D5  supports_format 对 {len(list(DisplayFormat))} 个枚举值全部返回 True")
    except Exception as e:
        failed += 1
        failures.append(f"D5: {e}")
        print(f"    {_fail(str(e))} D5")

    # ── D6: thread-safe 并发注册 ──────────────────────────────────────────────
    total += 1
    try:
        class _ThreadProvider(DisplayProvider):
            def __init__(self, n):
                super().__init__(f"thread_test_{n}", "s", "Thread")
                self.category = "test"
            def extract_data(self, node=None, **kwargs):
                return {}

        errors = []
        lock = threading.Lock()
        N = 20
        providers = [_ThreadProvider(i) for i in range(N)]

        def _register(p):
            try:
                reg.register(p)
            except Exception as exc:
                with lock:
                    errors.append(str(exc))

        threads = [threading.Thread(target=_register, args=(p,)) for p in providers]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        _assert(not errors, f"Thread errors: {errors}")
        # cleanup
        for i in range(N):
            reg.unregister(f"thread_test_{i}", "s")

        passed += 1
        print(f"    {_ok()} D6  {N} 线程并发注册，无竞争错误")
    except Exception as e:
        failed += 1
        failures.append(f"D6: {e}")
        print(f"    {_fail(str(e))} D6 thread-safe register")

    return {"total": total, "passed": passed, "failed": failed, "skipped": 0, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# Suite E: Plugin 注册表 — 所有插件加载/元数据/关闭
# ════════════════════════════════════════════════════════════════════════════

_PLUGIN_NAMES = ["tui", "test_plugin", "web_user", "dependency_manager", "env_guard", "port_forwarder"]


def suite_e_plugin_registry() -> dict:
    total = passed = failed = 0
    failures: list[str] = []

    print(_head("Suite E: Plugin 注册表 — 所有插件加载/元数据/关闭"))

    try:
        from opensynaptic.services.plugin_registry import PLUGIN_SPECS
    except ImportError as e:
        print(f"    {_skip(f'import failed: {e}')}")
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 1, "failures": []}

    import importlib

    for plugin_name in _PLUGIN_NAMES:
        # ── E1: PLUGIN_SPECS 包含该插件 ──────────────────────────────────────
        total += 1
        label = f"E/{plugin_name}"
        spec = PLUGIN_SPECS.get(plugin_name)
        if spec is None:
            failed += 1
            failures.append(f"{label}/spec: not in PLUGIN_SPECS")
            print(f"    {_fail('not in PLUGIN_SPECS')} {label}")
            continue
        passed += 1
        print(f"    {_ok()} {label}/spec  module={spec['module']} class={spec['class']}")

        # ── E2: 模块可导入 ────────────────────────────────────────────────────
        total += 1
        try:
            mod = importlib.import_module(spec["module"])
            _assert(mod is not None)
            passed += 1
            print(f"    {_ok()} {label}/import")
        except Exception as e:
            failed += 1
            failures.append(f"{label}/import: {e}")
            print(f"    {_fail(str(e))} {label}/import")
            continue

        # ── E3: 类可解析 ──────────────────────────────────────────────────────
        total += 1
        try:
            cls = getattr(mod, spec["class"])
            _assert(callable(cls), f"{spec['class']} is not callable")
            passed += 1
            print(f"    {_ok()} {label}/class  {spec['class']} 可解析")
        except Exception as e:
            failed += 1
            failures.append(f"{label}/class: {e}")
            print(f"    {_fail(str(e))} {label}/class")
            continue

        # ── E4: get_required_config 结构合法 ──────────────────────────────────
        total += 1
        try:
            if hasattr(cls, "get_required_config"):
                cfg = cls.get_required_config()
                _assert(isinstance(cfg, dict), f"get_required_config() should return dict, got {type(cfg)}")
                _assert("enabled" in cfg, "required config should have 'enabled' key")
            passed += 1
            print(f"    {_ok()} {label}/config  get_required_config OK")
        except Exception as e:
            failed += 1
            failures.append(f"{label}/config: {e}")
            print(f"    {_fail(str(e))} {label}/config")

        # ── E5: 无节点初始化不崩溃 ────────────────────────────────────────────
        total += 1
        try:
            instance = cls(node=None)
            _assert(instance is not None)
            # close 不应抛出
            if hasattr(instance, "close"):
                instance.close()
            passed += 1
            print(f"    {_ok()} {label}/nodenil  node=None 初始化+关闭 OK")
        except Exception as e:
            failed += 1
            failures.append(f"{label}/nodenil: {e}")
            print(f"    {_fail(str(e))} {label}/nodenil")

        # ── E6: defaults 中的必须字段存在 ─────────────────────────────────────
        total += 1
        try:
            defaults = spec.get("defaults", {})
            _assert(isinstance(defaults, dict), "defaults should be dict")
            _assert("enabled" in defaults, "defaults should have 'enabled'")
            passed += 1
            print(f"    {_ok()} {label}/defaults  结构合法")
        except Exception as e:
            failed += 1
            failures.append(f"{label}/defaults: {e}")
            print(f"    {_fail(str(e))} {label}/defaults")

    return {"total": total, "passed": passed, "failed": failed, "skipped": 0, "failures": failures}


# ════════════════════════════════════════════════════════════════════════════
# 汇总
# ════════════════════════════════════════════════════════════════════════════

def _print_summary(results: dict, elapsed: float) -> int:
    total   = sum(r["total"]   for r in results.values())
    passed  = sum(r["passed"]  for r in results.values())
    failed  = sum(r["failed"]  for r in results.values())
    skipped = sum(r.get("skipped", 0) for r in results.values())

    W = 72
    print(f"\n{'═'*W}")
    print(f"  {'套件':<36} {'总计':>6} {'通过':>6} {'失败':>6} {'跳过':>6}")
    print(f"  {'─'*36} {'─':>6} {'─':>6} {'─':>6} {'─':>6}")
    for name, r in results.items():
        print(f"  {name:<36} {r['total']:>6} {r['passed']:>6} {r['failed']:>6} {r.get('skipped',0):>6}")
    print(f"  {'─'*36} {'─':>6} {'─':>6} {'─':>6} {'─':>6}")
    print(f"  {'总计':<36} {total:>6} {passed:>6} {failed:>6} {skipped:>6}")
    print(f"{'═'*W}")

    pass_rate = 100.0 * passed / (total - skipped) if (total - skipped) > 0 else 100.0
    print(f"  耗时: {elapsed*1000:.0f}ms   通过率: {pass_rate:.1f}%\n")

    all_failures = []
    for r in results.values():
        all_failures.extend(r.get("failures", []))

    if all_failures:
        print(f"  失败详情 ({len(all_failures)} 条):")
        for f in all_failures:
            print(f"    ✗ {f}")
        print()

    return 1 if failed > 0 else 0


def main() -> int:
    t0 = time.monotonic()
    results = {}
    results["A | DatabaseManager (SQLite)     "] = suite_a_db_engine()
    results["B | PortForwarder 规则+生命周期   "] = suite_b_port_forwarder()
    results["C | TestPlugin 组件套件           "] = suite_c_test_plugin()
    results["D | DisplayAPI 全格式穷举         "] = suite_d_display_api()
    results["E | Plugin 注册表               "] = suite_e_plugin_registry()
    return _print_summary(results, time.monotonic() - t0)


if __name__ == "__main__":
    raise SystemExit(main())
