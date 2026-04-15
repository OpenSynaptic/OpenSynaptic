#!/usr/bin/env python3
"""
Enhanced Port Forwarder Smoke-Check

Quick sanity verification for EnhancedPortForwarder (v1.4.0+).

Checks (in order):
  1. Import chain (__init__ → main → enhanced)
  2. EnhancedPortForwarder is a subclass of PortForwarder
  3. get_required_config() contains all expected keys
  4. node=None lifecycle (init, close) does not crash
  5. FirewallRule allow/deny logic
  6. TrafficShaper non-blocking drop
  7. ProtocolConverter passthrough and transform
  8. Middleware before/after hooks
  9. ProxyRule fallback on network failure
 10. 7-step dispatch pipeline with mock original_dispatch
"""
from __future__ import annotations

import sys
import time
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH  = REPO_ROOT / "src"
for _p in (str(SRC_PATH), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_RESET = "\033[0m"
_GRN   = "\033[32m"
_RED   = "\033[31m"

def _ok(msg=""):   return f"{_GRN}PASS{_RESET}" + (f"  {msg}" if msg else "")
def _fail(msg=""): return f"{_RED}FAIL{_RESET}" + (f"  {msg}" if msg else "")

_checks = 0
_failures = 0


def check(label: str, expr: bool, detail: str = ""):
    global _checks, _failures
    _checks += 1
    if expr:
        print(f"  {_ok()} {label}")
    else:
        _failures += 1
        print(f"  {_fail(detail or 'assertion failed')} {label}")


def main() -> int:
    global _checks, _failures
    print(f"\nEnhanced Port Forwarder Smoke-Check (v1.4.0)\n{'─'*55}")

    # ── 1. Import chain ────────────────────────────────────────────────────
    try:
        from opensynaptic.services.port_forwarder import (
            PortForwarder, ForwardingRule, ForwardingRuleSet,
            EnhancedPortForwarder, FirewallRule, TrafficShaper,
            ProtocolConverter, Middleware, ProxyRule,
        )
        check("1. Import chain (__init__ → main + enhanced)", True)
    except ImportError as e:
        check("1. Import chain", False, str(e))
        print(f"\n{_fail()} Import failed – aborting smoke-check.\n")
        return 1

    pkt = b'\xAB' * 32

    # ── 2. Inheritance ─────────────────────────────────────────────────────
    check("2. EnhancedPortForwarder is subclass of PortForwarder",
          issubclass(EnhancedPortForwarder, PortForwarder))

    # ── 3. get_required_config ─────────────────────────────────────────────
    cfg = EnhancedPortForwarder.get_required_config()
    required_keys = ('enabled', 'rule_sets', 'persist_rules',
                     'firewall_enabled', 'traffic_shaping_enabled',
                     'protocol_conversion_enabled', 'middleware_enabled',
                     'proxy_enabled', 'firewall_rules_file')
    missing = [k for k in required_keys if k not in cfg]
    check("3. get_required_config has all expected keys",
          not missing, f"missing: {missing}")

    # ── 4. node=None lifecycle ─────────────────────────────────────────────
    try:
        epf = EnhancedPortForwarder(node=None, persist_rules=False)
        epf.close()
        check("4. node=None lifecycle (init + close) no crash", True)
    except Exception as e:
        check("4. node=None lifecycle", False, str(e))

    # ── 5. FirewallRule allow/deny ─────────────────────────────────────────
    try:
        epf = EnhancedPortForwarder(node=None, persist_rules=False)
        epf.add_firewall_rule(FirewallRule(name='block_udp', action='deny',
                                           from_protocol='UDP'))
        denied = not epf.check_firewall(pkt, 'UDP')
        allowed = epf.check_firewall(pkt, 'TCP')
        check("5. FirewallRule deny/allow", denied and allowed,
              f"denied={denied} allowed={allowed}")
    except Exception as e:
        check("5. FirewallRule", False, str(e))

    # ── 6. TrafficShaper non-blocking drop ────────────────────────────────
    try:
        epf = EnhancedPortForwarder(node=None, persist_rules=False)
        shaper = TrafficShaper(name='slow', rate_limit_bps=1, burst_capacity=1)
        epf.add_traffic_shaper('slow', shaper)
        shaper.can_send(1)  # exhaust
        t0 = time.monotonic()
        wt = epf.apply_traffic_shaping(pkt, 'slow')
        elapsed = time.monotonic() - t0
        check("6. TrafficShaper non-blocking drop (no sleep)",
              wt > 0 and elapsed < 0.5,
              f"wait_time={wt:.3f} elapsed={elapsed:.4f}s")
    except Exception as e:
        check("6. TrafficShaper", False, str(e))

    # ── 7. ProtocolConverter ───────────────────────────────────────────────
    try:
        epf = EnhancedPortForwarder(node=None, persist_rules=False)
        # Passthrough
        conv_pass = ProtocolConverter(name='p', from_protocol='UDP', to_protocol='TCP')
        epf.add_protocol_converter(conv_pass)
        out = epf.convert_protocol(pkt, 'UDP', 'TCP')
        passthrough_ok = (out == pkt)
        # Transform
        conv_xform = ProtocolConverter(name='x', from_protocol='A', to_protocol='B',
                                        transform_func=lambda p: b'XFORM')
        epf.add_protocol_converter(conv_xform)
        out2 = epf.convert_protocol(b'input', 'A', 'B')
        transform_ok = (out2 == b'XFORM')
        check("7. ProtocolConverter passthrough + transform",
              passthrough_ok and transform_ok,
              f"passthrough={passthrough_ok} transform={transform_ok}")
    except Exception as e:
        check("7. ProtocolConverter", False, str(e))

    # ── 8. Middleware before/after ────────────────────────────────────────
    try:
        epf = EnhancedPortForwarder(node=None, persist_rules=False)
        epf.add_middleware(Middleware(
            name='m',
            before_dispatch=lambda p, m: b'BEFORE',
            after_dispatch=lambda p, m, r: False,  # always returns False
        ))
        before_out = epf.execute_middlewares_before(pkt, 'UDP')
        after_out = epf.execute_middlewares_after(pkt, 'UDP', True)
        check("8. Middleware before/after hooks",
              before_out == b'BEFORE' and after_out is False,
              f"before={before_out!r} after={after_out}")
    except Exception as e:
        check("8. Middleware", False, str(e))

    # ── 9. ProxyRule fallback ──────────────────────────────────────────────
    try:
        proxy = ProxyRule(name='p1', from_protocol='UDP', to_protocol='UDP',
                          to_host='192.0.2.1', to_port=9999, timeout=0.1)
        result = proxy.forward(pkt)
        check("9. ProxyRule fallback to original packet on failure",
              result == pkt, f"got: {result!r}")
    except Exception as e:
        check("9. ProxyRule fallback", False, str(e))

    # ── 10. Full 7-step pipeline ──────────────────────────────────────────
    try:
        dispatched = []
        epf = EnhancedPortForwarder(node=None, persist_rules=False)
        epf.original_dispatch = lambda p, medium=None: dispatched.append((p, medium)) or True
        epf.is_hijacked = True

        result = epf._hijacked_dispatch(pkt, 'UDP')
        pipeline_ok = (result is True and len(dispatched) == 1
                       and dispatched[0][1] == 'UDP'
                       and epf.stats['total_packets'] == 1)
        check("10. 7-step dispatch pipeline calls original_dispatch",
              pipeline_ok,
              f"result={result} dispatched={len(dispatched)} "
              f"total={epf.stats['total_packets']} medium={dispatched[0][1] if dispatched else '?'}")
    except Exception as e:
        check("10. 7-step pipeline", False, str(e))

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n{'─'*55}")
    passed = _checks - _failures
    print(f"  {passed}/{_checks} checks passed", end="")
    if _failures == 0:
        print(f"  {_GRN}ALL OK{_RESET}\n")
        return 0
    else:
        print(f"  {_RED}{_failures} FAILED{_RESET}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
