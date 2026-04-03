#!/usr/bin/env python3
"""Exhaustive local simulation for PortForwarder protocol matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable


PROTOCOLS = (
    "UDP",
    "TCP",
    "UART",
    "RS485",
    "CAN",
    "LORA",
    "MQTT",
    "MATTER",
    "ZIGBEE",
    "BLUETOOTH",
)

TRANSPORT_PROTOCOLS = {"UDP", "TCP"}
APPLICATION_PROTOCOLS = {"MQTT", "MATTER", "ZIGBEE"}
PHYSICAL_PROTOCOLS = {"UART", "RS485", "CAN", "LORA", "BLUETOOTH"}


def _ensure_import_path() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


def _parse_list(value: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = (value or "").strip()
    if not raw:
        return default
    items = [x.strip().upper() for x in raw.split(",") if x.strip()]
    unknown = [x for x in items if x not in PROTOCOLS]
    if unknown:
        raise ValueError(f"unknown protocol(s): {unknown}")
    dedup: list[str] = []
    for item in items:
        if item not in dedup:
            dedup.append(item)
    return tuple(dedup)


def _iter_pairs(src: Iterable[str], dst: Iterable[str], include_self: bool) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for s in src:
        for d in dst:
            if not include_self and s == d:
                continue
            pairs.append((s, d))
    return pairs


def _base_resources() -> dict:
    return {
        "RESOURCES": {
            "transport_config": {"udp": {}, "tcp": {}},
            "application_config": {"mqtt": {}, "matter": {}, "zigbee": {}},
            "physical_config": {
                "uart": {},
                "rs485": {},
                "can": {},
                "lora": {},
                "bluetooth": {},
            },
        }
    }


class _FakeNode:
    def __init__(self):
        self.config = _base_resources()
        self.dispatch_calls: list[dict] = []

    def dispatch(self, packet: bytes, medium: str | None = None) -> bool:
        self.dispatch_calls.append(
            {
                "medium": str(medium or "").upper(),
                "size": len(packet),
            }
        )
        return True


def _assert_target_cfg(node: _FakeNode, to_protocol: str, to_host: str, to_port: int) -> tuple[bool, str]:
    resources = node.config.get("RESOURCES", {}) if isinstance(node.config, dict) else {}
    name = to_protocol.lower()

    if to_protocol in TRANSPORT_PROTOCOLS:
        section = resources.get("transport_config", {})
    elif to_protocol in APPLICATION_PROTOCOLS:
        section = resources.get("application_config", {})
    elif to_protocol in PHYSICAL_PROTOCOLS:
        section = resources.get("physical_config", {})
    else:
        return False, f"unknown target protocol: {to_protocol}"

    row = section.get(name, {}) if isinstance(section, dict) else {}
    if not isinstance(row, dict):
        return False, f"config row not dict for {to_protocol}"

    got_host = row.get("host")
    got_port = row.get("port")
    if got_host != to_host or got_port != to_port:
        return False, f"config mismatch for {to_protocol}: host={got_host!r}, port={got_port!r}"

    return True, ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exhaustive local PortForwarder matrix simulation")
    parser.add_argument(
        "--from-protocols",
        default="",
        help="Comma-separated source protocols (default: all supported)",
    )
    parser.add_argument(
        "--to-protocols",
        default="",
        help="Comma-separated target protocols (default: all supported)",
    )
    parser.add_argument(
        "--include-self",
        action="store_true",
        default=False,
        help="Include A->A pairs (default: excluded)",
    )
    parser.add_argument(
        "--json-out",
        default="",
        help="Optional path to write result JSON",
    )
    return parser.parse_args()


def main() -> int:
    repo_root = _ensure_import_path()

    from opensynaptic.services.port_forwarder.main import ForwardingRule, ForwardingRuleSet, PortForwarder

    args = parse_args()
    from_protocols = _parse_list(args.from_protocols, PROTOCOLS)
    to_protocols = _parse_list(args.to_protocols, PROTOCOLS)
    pairs = _iter_pairs(from_protocols, to_protocols, include_self=bool(args.include_self))

    node = _FakeNode()
    cfg = PortForwarder.get_required_config()
    cfg["persist_rules"] = False

    plugin = PortForwarder(node=node, **cfg)
    plugin.auto_load()

    failures: list[dict] = []
    packet = b"OSPFWDCHK\x00\x01\x02\x03"

    for idx, (src, dst) in enumerate(pairs, start=1):
        to_host = "127.0.0.1"
        to_port = 19000 + idx

        rule = ForwardingRule(
            from_protocol=src,
            to_protocol=dst,
            to_host=to_host,
            to_port=to_port,
            priority=100,
        )

        plugin.rule_sets[plugin.default_rule_set] = ForwardingRuleSet(
            name=plugin.default_rule_set,
            description="matrix simulation",
            enabled=True,
            rules=[rule],
        )

        before_calls = len(node.dispatch_calls)
        ok = node.dispatch(packet, medium=src)
        after_calls = len(node.dispatch_calls)

        call_ok = after_calls == before_calls + 1
        got_medium = node.dispatch_calls[-1].get("medium") if node.dispatch_calls else None
        route_ok = bool(ok) and call_ok and got_medium == dst

        cfg_ok, cfg_err = _assert_target_cfg(node, dst, to_host, to_port)

        rule_key = f"{src}→{dst}"
        stats_count = int(plugin.stats.get("rules_applied", {}).get(rule_key, 0))
        stats_ok = stats_count >= 1

        if not (route_ok and cfg_ok and stats_ok):
            failures.append(
                {
                    "from": src,
                    "to": dst,
                    "route_ok": route_ok,
                    "cfg_ok": cfg_ok,
                    "stats_ok": stats_ok,
                    "got_medium": got_medium,
                    "stats_count": stats_count,
                    "cfg_error": cfg_err,
                }
            )

    plugin.close()

    report = {
        "ok": len(failures) == 0,
        "total_pairs": len(pairs),
        "passed_pairs": len(pairs) - len(failures),
        "failed_pairs": len(failures),
        "include_self": bool(args.include_self),
        "from_protocols": list(from_protocols),
        "to_protocols": list(to_protocols),
        "sample_failures": failures[:20],
    }

    payload = json.dumps(report, ensure_ascii=False)
    print(payload)

    out = str(args.json_out or "").strip()
    if out:
        out_path = Path(out)
        if not out_path.is_absolute():
            out_path = repo_root / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
