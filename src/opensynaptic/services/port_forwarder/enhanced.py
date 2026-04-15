"""
Enhanced Port Forwarder – Firewall, Traffic Shaping, Middleware, Proxy

Extends PortForwarder (main.py) with advanced network management:
  - FirewallRule        – packet allow/deny by protocol, IP, port, size
  - TrafficShaper       – token-bucket rate-limiting with non-blocking drop
  - ProtocolConverter   – packet-level conversion with optional transform func
  - Middleware          – pre/post dispatch hooks
  - ProxyRule           – real UDP/TCP socket-level forwarding with fallback

Architecture:
    EnhancedPortForwarder(PortForwarder)
    ├── ForwardingRule / ForwardingRuleSet  ← inherited from main.py
    ├── FirewallRule
    ├── TrafficShaper
    ├── ProtocolConverter
    ├── Middleware
    └── ProxyRule

Dispatch pipeline (7 steps, overrides parent _hijacked_dispatch):
    1. Middleware before
    2. Firewall check  → drop if denied
    3. Traffic shaping → non-blocking drop if over limit
    4. Protocol conversion
    5. Proxy (if rule registered for this medium)
    6. PortForwarder routing (_matches_rule + _update_transport + original_dispatch)
    7. Middleware after
"""

import socket
import threading
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

from opensynaptic.utils import os_log, read_json, write_json, ctx
from opensynaptic.services.port_forwarder.main import (
    PortForwarder, ForwardingRule, ForwardingRuleSet,
)

_PROXY_DEFAULT_TIMEOUT = 2.0  # seconds


# ════════════════════════════════════════════════════════════════════════════
# 1. Firewall Rule
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class FirewallRule:
    """
    Firewall rule – controls packet allow/deny.

    Filtering dimensions:
      - Protocol (from_protocol)
      - Source IP (from_ip)
      - Source port range (from_port_range): (min_port, max_port) inclusive
      - Destination port range (to_port_range): (min_port, max_port) inclusive
      - Packet size limits (packet_size_min / packet_size_max)
    """

    name: str
    action: str                                    # 'allow' or 'deny'
    from_protocol: Optional[str] = None
    from_ip: Optional[str] = None
    from_port_range: Optional[tuple] = None        # (min_port, max_port) inclusive
    to_port_range: Optional[tuple] = None          # (min_port, max_port) inclusive
    packet_size_min: Optional[int] = None
    packet_size_max: Optional[int] = None
    enabled: bool = True
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def matches(self, packet: bytes, from_proto: str, from_ip: str = None,
                from_port: int = None, to_port: int = None) -> bool:
        """Return True if this rule matches the given packet attributes."""
        if self.from_protocol and from_proto.upper() != self.from_protocol.upper():
            return False
        if self.from_ip and from_ip is not None and from_ip != self.from_ip:
            return False
        if self.from_port_range and from_port is not None:
            lo, hi = self.from_port_range
            if not (lo <= from_port <= hi):
                return False
        if self.to_port_range and to_port is not None:
            lo, hi = self.to_port_range
            if not (lo <= to_port <= hi):
                return False
        pkt_len = len(packet)
        if self.packet_size_min is not None and pkt_len < self.packet_size_min:
            return False
        if self.packet_size_max is not None and pkt_len > self.packet_size_max:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            'name': self.name,
            'action': self.action,
            'from_protocol': self.from_protocol,
            'from_ip': self.from_ip,
            'from_port_range': list(self.from_port_range) if self.from_port_range else None,
            'to_port_range': list(self.to_port_range) if self.to_port_range else None,
            'packet_size_min': self.packet_size_min,
            'packet_size_max': self.packet_size_max,
            'enabled': self.enabled,
            'priority': self.priority,
            'metadata': self.metadata,
        }

    @staticmethod
    def from_dict(data: dict) -> 'FirewallRule':
        d = dict(data)
        if d.get('from_port_range') is not None:
            d['from_port_range'] = tuple(d['from_port_range'])
        if d.get('to_port_range') is not None:
            d['to_port_range'] = tuple(d['to_port_range'])
        return FirewallRule(**d)


# ════════════════════════════════════════════════════════════════════════════
# 2. Traffic Shaper
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class TrafficShaper:
    """
    Token-bucket rate limiter.

    Call can_send(packet_size) → bool.
    Returns False when the bucket is empty; the caller MUST drop the packet
    immediately (non-blocking).  Blocking with sleep() is intentionally not
    supported.
    """

    name: str
    rate_limit_bps: int    # bytes per second
    burst_capacity: int    # maximum burst size in bytes
    enabled: bool = True

    def __post_init__(self):
        self.tokens: float = float(self.burst_capacity)
        self.last_refill: float = time.time()
        self._lock = threading.Lock()

    def can_send(self, packet_size: int) -> bool:
        """Return True if packet may be sent; caller must drop if False."""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_refill
            self.tokens = min(
                float(self.burst_capacity),
                self.tokens + elapsed * self.rate_limit_bps,
            )
            self.last_refill = now
            if self.tokens >= packet_size:
                self.tokens -= packet_size
                return True
            return False

    def get_wait_time(self, packet_size: int) -> float:
        """Return the hypothetical wait-seconds (informational only; do NOT sleep)."""
        with self._lock:
            deficit = packet_size - self.tokens
            if deficit <= 0:
                return 0.0
            return deficit / max(self.rate_limit_bps, 1)


# ════════════════════════════════════════════════════════════════════════════
# 3. Protocol Converter
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ProtocolConverter:
    """
    Packet-level protocol converter.

    If transform_func is provided it is called as transform_func(packet) -> bytes.
    Without a transform_func the packet passes through unchanged (the converter
    acts purely as an audit/logging point).
    """

    name: str
    from_protocol: str
    to_protocol: str
    transform_func: Optional[Callable] = None
    enabled: bool = True

    def convert(self, packet: bytes) -> bytes:
        """Apply conversion; return the (possibly modified) packet."""
        if self.transform_func:
            return self.transform_func(packet)
        return packet


# ════════════════════════════════════════════════════════════════════════════
# 4. Middleware
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class Middleware:
    """
    Pre/post dispatch hooks.

    before_dispatch(packet, medium) -> bytes  – may modify the packet.
    after_dispatch(packet, medium, result) -> bool – may change the result.
    """

    name: str
    before_dispatch: Optional[Callable] = None
    after_dispatch: Optional[Callable] = None
    enabled: bool = True

    def execute_before(self, packet: bytes, medium: str) -> bytes:
        if self.enabled and self.before_dispatch:
            return self.before_dispatch(packet, medium)
        return packet

    def execute_after(self, packet: bytes, medium: str, result: bool) -> bool:
        if self.enabled and self.after_dispatch:
            return self.after_dispatch(packet, medium, result)
        return result


# ════════════════════════════════════════════════════════════════════════════
# 5. Proxy Rule
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ProxyRule:
    """
    Real UDP/TCP socket-level forwarding proxy.

    For each matching medium the outgoing packet is sent verbatim to
    (to_host, to_port) using to_protocol.  If a response is received within
    `timeout` seconds it replaces the packet before normal dispatch;
    otherwise the original packet passes through unchanged.

    backup_hosts: tried in order when the primary host fails.
    """

    name: str
    from_protocol: str
    to_protocol: str
    to_host: str
    to_port: int
    timeout: float = _PROXY_DEFAULT_TIMEOUT
    backup_hosts: List[str] = field(default_factory=list)
    enabled: bool = True

    # Runtime stats (not persisted)
    request_count: int = field(default=0, repr=False)
    response_count: int = field(default=0, repr=False)
    error_count: int = field(default=0, repr=False)

    def __post_init__(self):
        self._lock = threading.Lock()

    def _forward_udp(self, packet: bytes, host: str) -> Optional[bytes]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(self.timeout)
                sock.sendto(packet, (host, self.to_port))
                response, _ = sock.recvfrom(65535)
                return response
        except (socket.timeout, OSError):
            return None

    def _forward_tcp(self, packet: bytes, host: str) -> Optional[bytes]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect((host, self.to_port))
                sock.sendall(packet)
                chunks: List[bytes] = []
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
                return b''.join(chunks) if chunks else None
        except (socket.timeout, OSError):
            return None

    def forward(self, packet: bytes) -> bytes:
        """
        Forward packet; return response or original packet on failure.
        Tries primary host then each backup_host in order.
        """
        with self._lock:
            self.request_count += 1
        proto = self.to_protocol.upper()
        hosts = [self.to_host] + list(self.backup_hosts)
        for host in hosts:
            try:
                if proto == 'UDP':
                    response = self._forward_udp(packet, host)
                elif proto == 'TCP':
                    response = self._forward_tcp(packet, host)
                else:
                    response = None
                if response is not None:
                    with self._lock:
                        self.response_count += 1
                    return response
            except Exception:
                pass
        with self._lock:
            self.error_count += 1
        return packet  # pass-through fallback


# ════════════════════════════════════════════════════════════════════════════
# 6. Enhanced Port Forwarder
# ════════════════════════════════════════════════════════════════════════════

class EnhancedPortForwarder(PortForwarder):
    """
    Extended port forwarder with firewall, traffic shaping, middleware and proxy.

    Inherits all ForwardingRule / ForwardingRuleSet / persistence / CLI from
    PortForwarder and wraps _hijacked_dispatch with a 7-step pipeline.
    """

    def __init__(self, node=None, **kwargs):
        super().__init__(node, **kwargs)

        # Feature flags (each subsystem can be toggled independently)
        self.features_enabled: Dict[str, bool] = {
            'firewall':            bool((self.config or {}).get('firewall_enabled', True)),
            'traffic_shaping':     bool((self.config or {}).get('traffic_shaping_enabled', True)),
            'protocol_conversion': bool((self.config or {}).get('protocol_conversion_enabled', True)),
            'middleware':          bool((self.config or {}).get('middleware_enabled', True)),
            'proxy':               bool((self.config or {}).get('proxy_enabled', True)),
        }

        # Enhanced component registries
        self.firewall_rules: List[FirewallRule] = []
        self.traffic_shapers: Dict[str, TrafficShaper] = {}
        self.protocol_converters: Dict[str, ProtocolConverter] = {}
        self.middlewares: List[Middleware] = []
        self.proxy_rules: Dict[str, ProxyRule] = {}

        # Extend parent stats dict with enhanced counters
        self.stats.update({
            'allowed_packets': 0,
            'denied_packets': 0,
            'converted_packets': 0,
            'proxied_packets': 0,
            'shaped_dropped_packets': 0,
            'middleware_executed': 0,
        })

        # Load persisted firewall rules
        self._load_firewall_from_file()

    # ─── Config ──────────────────────────────────────────────────────────────

    @staticmethod
    def get_required_config() -> dict:
        base = PortForwarder.get_required_config()
        base.update({
            'firewall_enabled': True,
            'traffic_shaping_enabled': True,
            'protocol_conversion_enabled': True,
            'middleware_enabled': True,
            'proxy_enabled': True,
            'firewall_rules_file': 'data/port_forwarder_firewall.json',
        })
        return base

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    def auto_load(self, config=None):
        result = super().auto_load(config)
        self._load_firewall_from_file()
        return result

    def close(self):
        self._save_firewall_to_file()
        super().close()

    # ─── Firewall persistence ─────────────────────────────────────────────────

    def _firewall_file_path(self) -> Path:
        raw = str((self.config or {}).get('firewall_rules_file', '') or '').strip()
        if not raw:
            raw = 'data/port_forwarder_firewall.json'
        p = Path(raw)
        if p.is_absolute():
            return p
        return Path(ctx.root) / p

    def _load_firewall_from_file(self):
        if not bool((self.config or {}).get('persist_rules', True)):
            return
        path = self._firewall_file_path()
        payload = read_json(str(path))
        if not isinstance(payload, dict):
            return
        loaded: List[FirewallRule] = []
        for item in payload.get('firewall_rules', []):
            try:
                loaded.append(FirewallRule.from_dict(item))
            except Exception as exc:
                os_log.err('ENHANCED_PF', 'LOAD_FIREWALL_FILE', exc, {'item': str(item)[:200]})
        if loaded:
            with self._lock:
                self.firewall_rules = loaded

    def _save_firewall_to_file(self) -> bool:
        if not bool((self.config or {}).get('persist_rules', True)):
            return True
        with self._lock:
            path = self._firewall_file_path()
            payload = {
                'updated_at': int(time.time()),
                'firewall_rules': [r.to_dict() for r in self.firewall_rules],
            }
        ok = write_json(str(path), payload)
        if not ok:
            os_log.err('ENHANCED_PF', 'SAVE_FIREWALL_FILE',
                       RuntimeError('write_json failed'), {'path': str(path)})
        return bool(ok)

    # ─── Feature toggle API ───────────────────────────────────────────────────

    def enable_feature(self, feature: str) -> bool:
        with self._lock:
            if feature not in self.features_enabled:
                return False
            self.features_enabled[feature] = True
            return True

    def disable_feature(self, feature: str) -> bool:
        with self._lock:
            if feature not in self.features_enabled:
                return False
            self.features_enabled[feature] = False
            return True

    def toggle_feature(self, feature: str):
        with self._lock:
            if feature not in self.features_enabled:
                return None
            self.features_enabled[feature] = not self.features_enabled[feature]
            return self.features_enabled[feature]

    def get_feature_status(self) -> dict:
        with self._lock:
            return dict(self.features_enabled)

    def set_features(self, **kwargs) -> dict:
        with self._lock:
            for feature, enabled in kwargs.items():
                if feature in self.features_enabled:
                    self.features_enabled[feature] = bool(enabled)
            return dict(self.features_enabled)

    # ─── Firewall API ─────────────────────────────────────────────────────────

    def add_firewall_rule(self, rule: FirewallRule):
        with self._lock:
            self.firewall_rules.append(rule)
            self.firewall_rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_firewall_rule(self, name: str) -> bool:
        with self._lock:
            before = len(self.firewall_rules)
            self.firewall_rules = [r for r in self.firewall_rules if r.name != name]
            return len(self.firewall_rules) < before

    def check_firewall(self, packet: bytes, medium: str) -> bool:
        """Return True if allowed, False if denied."""
        if not self.features_enabled.get('firewall', True):
            return True
        with self._lock:
            for rule in self.firewall_rules:
                if not rule.enabled:
                    continue
                if rule.matches(packet, medium or ''):
                    if rule.action == 'deny':
                        self.stats['denied_packets'] += 1
                        os_log.info('ENHANCED_PF', 'FIREWALL_DENY',
                                    f'Denied by rule: {rule.name}',
                                    {'rule': rule.name, 'medium': medium})
                        return False
                    if rule.action == 'allow':
                        self.stats['allowed_packets'] += 1
                        return True
        self.stats['allowed_packets'] += 1
        return True  # default-allow

    # ─── Traffic shaping API ──────────────────────────────────────────────────

    def add_traffic_shaper(self, name: str, shaper: TrafficShaper):
        with self._lock:
            self.traffic_shapers[name] = shaper

    def apply_traffic_shaping(self, packet: bytes, shaper_name: str) -> float:
        """Return wait_time > 0 if packet should be dropped; 0.0 if allowed."""
        if not self.features_enabled.get('traffic_shaping', True):
            return 0.0
        with self._lock:
            shaper = self.traffic_shapers.get(shaper_name)
            if not shaper or not shaper.enabled:
                return 0.0
        if shaper.can_send(len(packet)):
            return 0.0
        return shaper.get_wait_time(len(packet))

    # ─── Protocol conversion API ──────────────────────────────────────────────

    def add_protocol_converter(self, converter: ProtocolConverter):
        with self._lock:
            key = f'{converter.from_protocol}→{converter.to_protocol}'
            self.protocol_converters[key] = converter

    def convert_protocol(self, packet: bytes, from_proto: str, to_proto: str) -> bytes:
        if not self.features_enabled.get('protocol_conversion', True):
            return packet
        with self._lock:
            key = f'{from_proto}→{to_proto}'
            converter = self.protocol_converters.get(key)
        if converter and converter.enabled:
            result = converter.convert(packet)
            with self._lock:
                self.stats['converted_packets'] += 1
            return result
        return packet

    # ─── Middleware API ────────────────────────────────────────────────────────

    def add_middleware(self, middleware: Middleware):
        with self._lock:
            self.middlewares.append(middleware)

    def execute_middlewares_before(self, packet: bytes, medium: str) -> bytes:
        if not self.features_enabled.get('middleware', True):
            return packet
        with self._lock:
            mw_list = list(self.middlewares)
        for mw in mw_list:
            packet = mw.execute_before(packet, medium or '')
            with self._lock:
                self.stats['middleware_executed'] += 1
        return packet

    def execute_middlewares_after(self, packet: bytes, medium: str, result: bool) -> bool:
        if not self.features_enabled.get('middleware', True):
            return result
        with self._lock:
            mw_list = list(self.middlewares)
        for mw in mw_list:
            result = mw.execute_after(packet, medium or '', result)
        return result

    # ─── Proxy API ─────────────────────────────────────────────────────────────

    def add_proxy_rule(self, rule: ProxyRule):
        with self._lock:
            self.proxy_rules[rule.name] = rule

    def apply_proxy(self, packet: bytes, rule_name: str) -> tuple:
        """Apply proxy rule; return (possibly_modified_packet, success)."""
        if not self.features_enabled.get('proxy', True):
            return packet, True
        with self._lock:
            proxy = self.proxy_rules.get(rule_name)
        if not proxy or not proxy.enabled:
            return packet, True
        try:
            result = proxy.forward(packet)
            with self._lock:
                self.stats['proxied_packets'] += 1
            return result, True
        except Exception as exc:
            os_log.err('ENHANCED_PF', 'PROXY_ERROR', exc, {'rule': rule_name})
            return packet, True

    # ─── 7-step dispatch override ─────────────────────────────────────────────

    def _hijacked_dispatch(self, packet: bytes, medium: Optional[str] = None) -> bool:
        """
        7-step dispatch pipeline, completely overriding parent:
          1) Middleware before
          2) Firewall check → return False if denied
          3) Traffic shaping → non-blocking drop if over limit
          4) Protocol conversion
          5) Proxy (if rule registered for this medium)
          6) PortForwarder routing (_matches_rule + _update_transport + dispatch)
          7) Middleware after
        """
        with self._lock:
            self.stats['total_packets'] += 1
            try:
                # Step 1 – pre-middleware
                packet = self.execute_middlewares_before(packet, medium)

                # Step 2 – firewall
                if not self.check_firewall(packet, medium):
                    return False

                # Step 3 – traffic shaping (non-blocking drop)
                wait_time = self.apply_traffic_shaping(packet, medium or 'default')
                if wait_time > 0:
                    self.stats['shaped_dropped_packets'] += 1
                    os_log.info('ENHANCED_PF', 'TRAFFIC_DROP',
                                f'Dropped: shaper needs {wait_time:.3f}s',
                                {'medium': medium, 'wait_time': wait_time})
                    return False

                # Step 4 – protocol conversion
                packet = self.convert_protocol(packet, medium or '', medium or '')

                # Step 5 – proxy (keyed by medium name)
                if self.features_enabled.get('proxy', True) and medium in self.proxy_rules:
                    packet, _ = self.apply_proxy(packet, medium)

                # Step 6 – routing + original_dispatch (no lock re-entry needed)
                success = self._route_and_dispatch(packet, medium)

                # Step 7 – post-middleware
                success = self.execute_middlewares_after(packet, medium, success)

                return success

            except Exception as exc:
                os_log.err('ENHANCED_PF', 'HIJACKED_DISPATCH', exc, {'medium': medium})
                return self.original_dispatch(packet, medium=medium)

    def _route_and_dispatch(self, packet: bytes, medium: Optional[str]) -> bool:
        """
        Reproduce PortForwarder routing without re-acquiring self._lock
        (already held by caller) and without double-counting total_packets.
        """
        target_medium = medium
        applied_rule = None

        for rule_set in self.rule_sets.values():
            if not rule_set.enabled:
                continue
            for rule in rule_set.get_rules_sorted():
                if self._matches_rule(packet, medium, rule):
                    target_medium = rule.to_protocol
                    applied_rule = rule
                    self._update_transport_config(rule)
                    rule_key = f'{rule.from_protocol}→{rule.to_protocol}'
                    self.stats['rules_applied'][rule_key] = (
                        self.stats['rules_applied'].get(rule_key, 0) + 1
                    )
                    os_log.info('ENHANCED_PF', 'RULE_APPLIED',
                                f'{rule_key} → {rule.to_host}:{rule.to_port}',
                                {'rule': rule_key})
                    break

        success = self.original_dispatch(packet, medium=target_medium)
        if success:
            if applied_rule:
                self.stats['forwarded_packets'] += 1
            else:
                self.stats['original_packets'] += 1
        else:
            self.stats['failed_forwards'] += 1
        return success

    # ─── CLI commands ──────────────────────────────────────────────────────────

    def get_cli_commands(self) -> dict:
        cmds = super().get_cli_commands()
        cmds.update({
            'features':        self.handle_features,
            'feature-enable':  self.handle_feature_enable,
            'feature-disable': self.handle_feature_disable,
            'firewall-list':   self.handle_firewall_list,
            'firewall-add':    self.handle_firewall_add,
            'firewall-remove': self.handle_firewall_remove,
            'shaper-add':      self.handle_shaper_add,
            'shaper-list':     self.handle_shaper_list,
            'middleware-list': self.handle_middleware_list,
        })
        return cmds

    def get_cli_completions(self) -> dict:
        comp = super().get_cli_completions()
        comp.update({
            'features':        'Show all feature flags and their on/off state',
            'feature-enable':  'Enable a feature (firewall/traffic_shaping/…)',
            'feature-disable': 'Disable a feature',
            'firewall-list':   'List all firewall rules',
            'firewall-add':    'Add a firewall rule (--name --action allow|deny --from-protocol)',
            'firewall-remove': 'Remove a firewall rule by name (--name)',
            'shaper-add':      'Add a traffic shaper (--name --rate-bps --burst)',
            'shaper-list':     'List all traffic shapers',
            'middleware-list': 'List all registered middleware',
        })
        return comp

    def handle_status(self, args, **kwargs) -> dict:
        base = super().handle_status(args, **kwargs)
        with self._lock:
            base.update({
                'features': dict(self.features_enabled),
                'firewall_rules': len(self.firewall_rules),
                'traffic_shapers': len(self.traffic_shapers),
                'protocol_converters': len(self.protocol_converters),
                'middlewares': len(self.middlewares),
                'proxy_rules': len(self.proxy_rules),
            })
        return base

    def handle_features(self, args, **kwargs) -> dict:
        with self._lock:
            return {
                'features': {
                    k: {'enabled': v, 'status': '✅ on' if v else '❌ off'}
                    for k, v in self.features_enabled.items()
                }
            }

    def handle_feature_enable(self, args, **kwargs) -> dict:
        feature = getattr(args, 'feature', None)
        if not feature:
            return {'status': 'error', 'message': 'feature name required'}
        ok = self.enable_feature(feature)
        if ok:
            return {'status': 'ok', 'message': f'{feature} enabled'}
        return {'status': 'error', 'message': f'Unknown feature: {feature}'}

    def handle_feature_disable(self, args, **kwargs) -> dict:
        feature = getattr(args, 'feature', None)
        if not feature:
            return {'status': 'error', 'message': 'feature name required'}
        ok = self.disable_feature(feature)
        if ok:
            return {'status': 'ok', 'message': f'{feature} disabled'}
        return {'status': 'error', 'message': f'Unknown feature: {feature}'}

    def handle_enable(self, args, **kwargs) -> dict:
        return self.handle_feature_enable(args, **kwargs)

    def handle_disable(self, args, **kwargs) -> dict:
        return self.handle_feature_disable(args, **kwargs)

    def handle_toggle(self, args, **kwargs) -> dict:
        feature = getattr(args, 'feature', None)
        if not feature:
            return {'status': 'error', 'message': 'feature name required'}
        new_state = self.toggle_feature(feature)
        if new_state is None:
            return {'status': 'error', 'message': f'Unknown feature: {feature}'}
        return {'status': 'ok', 'message': f'{feature} is now {"enabled" if new_state else "disabled"}'}

    def handle_firewall_list(self, args, **kwargs) -> dict:
        with self._lock:
            return {
                'rules': [r.to_dict() for r in self.firewall_rules],
                'total': len(self.firewall_rules),
            }

    def handle_firewall_add(self, args, **kwargs) -> dict:
        try:
            name = getattr(args, 'name', f'rule_{len(self.firewall_rules)}')
            action = getattr(args, 'action', 'allow')
            from_protocol = getattr(args, 'from_protocol', None)
            rule = FirewallRule(name=name, action=action, from_protocol=from_protocol)
            self.add_firewall_rule(rule)
            self._save_firewall_to_file()
            return {'status': 'ok', 'message': f'Added firewall rule: {name} ({action})'}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    def handle_firewall_remove(self, args, **kwargs) -> dict:
        name = getattr(args, 'name', None)
        if not name:
            return {'status': 'error', 'message': 'rule name required (--name)'}
        removed = self.remove_firewall_rule(name)
        if removed:
            self._save_firewall_to_file()
            return {'status': 'ok', 'message': f'Removed firewall rule: {name}'}
        return {'status': 'error', 'message': f'Rule not found: {name}'}

    def handle_shaper_add(self, args, **kwargs) -> dict:
        try:
            name = getattr(args, 'name', 'default')
            rate_bps = int(getattr(args, 'rate_bps', 1024))
            burst = int(getattr(args, 'burst', rate_bps * 2))
            shaper = TrafficShaper(name=name, rate_limit_bps=rate_bps, burst_capacity=burst)
            self.add_traffic_shaper(name, shaper)
            return {'status': 'ok', 'message': f'Added shaper: {name} ({rate_bps} B/s)'}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}

    def handle_shaper_list(self, args, **kwargs) -> dict:
        with self._lock:
            return {
                'shapers': [
                    {'name': s.name, 'rate_bps': s.rate_limit_bps,
                     'burst': s.burst_capacity, 'enabled': s.enabled}
                    for s in self.traffic_shapers.values()
                ],
                'total': len(self.traffic_shapers),
            }

    def handle_middleware_list(self, args, **kwargs) -> dict:
        with self._lock:
            return {
                'middlewares': [
                    {'name': m.name, 'enabled': m.enabled,
                     'has_before': m.before_dispatch is not None,
                     'has_after': m.after_dispatch is not None}
                    for m in self.middlewares
                ],
                'total': len(self.middlewares),
            }

    def get_stats(self) -> dict:
        with self._lock:
            result = dict(self.stats)
            result['features_enabled'] = dict(self.features_enabled)
            return result

    def handle_stats(self, args, **kwargs) -> dict:
        with self._lock:
            return {'statistics': self.get_stats()}
