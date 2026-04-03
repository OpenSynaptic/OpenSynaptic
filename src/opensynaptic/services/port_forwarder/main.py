"""
Port Forwarder Plugin – Advanced port forwarding via dispatch hijacking.

This plugin intercepts OpenSynaptic dispatch() calls and routes packets to
different ports/protocols based on configurable rules.

Architecture:
    ForwardingRule      → Individual routing rule (from_protocol/port → to_protocol/host/port)
    PortForwarder       → Main plugin that hijacks dispatch() and applies rules
    ServiceManager      → Mounts and manages the plugin lifecycle

Usage:
    # Create forwarding rules as Python objects
    rule1 = ForwardingRule(
        from_protocol='UDP',
        from_port=9999,
        to_protocol='TCP',
        to_host='192.168.1.100',
        to_port=8080,
    )
    
    # Mount plugin with rules
    plugin = PortForwarder(
        node=node,
        rules=[rule1, rule2, ...]
    )
    node.service_manager.mount('port_forwarder', plugin)
    node.service_manager.load('port_forwarder')
"""

import threading
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

from opensynaptic.utils import os_log, LogMsg, read_json, write_json, ctx
from opensynaptic.services.display_api import DisplayProvider, get_display_registry


# ════════════════════════════════════════════════════════════════════════════
# 1. Forwarding Rule Object Model
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ForwardingRule:
    """
    A single forwarding rule that maps packets from one protocol/port
    to another protocol/host/port.
    
    Attributes:
        from_protocol: Source protocol (e.g., 'UDP', 'TCP', 'UART')
        from_port: Source port number (optional for non-IP protocols)
        to_protocol: Destination protocol
        to_host: Destination host/IP
        to_port: Destination port
        enabled: Whether this rule is active
        priority: Rule priority (higher number = higher priority)
        condition: Optional lambda to check packet (for advanced filtering)
        metadata: Custom metadata dict
    """
    
    from_protocol: str
    to_protocol: str
    to_host: str
    to_port: int
    from_port: Optional[int] = None
    enabled: bool = True
    priority: int = 0
    condition: Optional[str] = None  # Serializable condition (not lambda)
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate rule after creation"""
        if self.metadata is None:
            self.metadata = {}
        
        # Validate protocols
        valid_protocols = {'UDP', 'TCP', 'UART', 'RS485', 'CAN', 'LORA', 
                          'MQTT', 'MATTER', 'ZIGBEE', 'BLUETOOTH'}
        if self.from_protocol.upper() not in valid_protocols:
            raise ValueError(f'Invalid from_protocol: {self.from_protocol}')
        if self.to_protocol.upper() not in valid_protocols:
            raise ValueError(f'Invalid to_protocol: {self.to_protocol}')
        
        # Normalize protocol names
        self.from_protocol = self.from_protocol.upper()
        self.to_protocol = self.to_protocol.upper()
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'from_protocol': self.from_protocol,
            'from_port': self.from_port,
            'to_protocol': self.to_protocol,
            'to_host': self.to_host,
            'to_port': self.to_port,
            'enabled': self.enabled,
            'priority': self.priority,
            'condition': self.condition,
            'metadata': self.metadata,
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'ForwardingRule':
        """Create rule from dictionary"""
        return ForwardingRule(**data)


@dataclass
class ForwardingRuleSet:
    """
    A collection of forwarding rules with metadata.
    
    Attributes:
        name: Name of this rule set
        description: Human-readable description
        rules: List of ForwardingRule objects
        enabled: Whether this rule set is active
    """
    
    name: str
    rules: List[ForwardingRule]
    description: str = ""
    enabled: bool = True
    
    def add_rule(self, rule: ForwardingRule):
        """Add a rule to this set"""
        self.rules.append(rule)
    
    def remove_rule(self, rule: ForwardingRule):
        """Remove a rule from this set"""
        self.rules.remove(rule)
    
    def get_rules_sorted(self) -> List[ForwardingRule]:
        """Get rules sorted by priority (descending)"""
        return sorted(
            [r for r in self.rules if r.enabled],
            key=lambda r: r.priority,
            reverse=True
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'description': self.description,
            'enabled': self.enabled,
            'rules': [r.to_dict() for r in self.rules],
        }
    
    @staticmethod
    def from_dict(data: dict) -> 'ForwardingRuleSet':
        """Create rule set from dictionary"""
        rules = [ForwardingRule.from_dict(r) for r in data.get('rules', [])]
        return ForwardingRuleSet(
            name=data['name'],
            rules=rules,
            description=data.get('description', ''),
            enabled=data.get('enabled', True),
        )


class PortForwarderDisplayProvider(DisplayProvider):
    """Display port forwarder runtime and rule summary."""

    def __init__(self, plugin_ref):
        super().__init__(plugin_name='port_forwarder', section_id='rules', display_name='Port Forwarding Rules')
        self.category = 'plugin'
        self.priority = 68
        self.refresh_interval_s = 2.0
        self._plugin = plugin_ref

    def extract_data(self, node=None, **kwargs):
        _ = node, kwargs
        plugin = self._plugin
        return {
            'initialized': bool(getattr(plugin, '_initialized', False)),
            'hijacked': bool(getattr(plugin, 'is_hijacked', False)),
            'rule_sets': list(getattr(plugin, 'rule_sets', {}).keys()),
            'total_rules': sum(len(rs.rules) for rs in getattr(plugin, 'rule_sets', {}).values()),
            'stats': plugin.get_stats(),
        }


# ════════════════════════════════════════════════════════════════════════════
# 2. Main Port Forwarder Plugin
# ════════════════════════════════════════════════════════════════════════════

class PortForwarder:
    """
    Main port forwarding plugin.
    
    Features:
        - Hijacks OpenSynaptic.dispatch() method
        - Routes packets based on configurable rules
        - Supports multiple protocols and rule sets
        - Thread-safe with locking
        - Persistent rule storage
        - CLI commands for management
    
    2026 规范：
        - 线程安全：是（使用 self._lock）
        - Display Providers：port_forwarder:rules
    
    Usage:
        plugin = PortForwarder(
            node=node,
            rules=[...]
        )
        node.service_manager.mount('port_forwarder', plugin)
        node.service_manager.load('port_forwarder')
    """
    
    def __init__(self, node=None, **kwargs):
        """
        初始化端口转发插件（按 2026 规范）
        
        参数：
            node: OpenSynaptic 节点实例
            **kwargs: 配置字典
        """
        self.node = node
        self.config = kwargs or {}
        self._lock = threading.RLock()
        
        # 规则存储
        self.rule_sets: Dict[str, ForwardingRuleSet] = {}
        self.default_rule_set = 'default'
        
        # 统计信息
        self.stats = {
            'total_packets': 0,
            'forwarded_packets': 0,
            'original_packets': 0,
            'failed_forwards': 0,
            'rules_applied': {},
        }
        
        # 原始 dispatch 用于恢复
        self.original_dispatch = None
        self.is_hijacked = False
        self._initialized = False
        
        # 从配置加载规则
        self._load_rules_from_config()
        
        os_log.log_with_const('info', LogMsg.PLUGIN_INIT, 
                             plugin='PortForwarder')
    
    @staticmethod
    def get_required_config() -> dict:
        """返回默认配置（按 2026 规范）"""
        return {
            'enabled': True,
            'mode': 'auto',
            'rule_sets': [
                {
                    'name': 'default',
                    'description': 'Default forwarding rules',
                    'enabled': True,
                    'rules': [],
                }
            ],
            'persist_rules': True,
            'rules_file': 'data/port_forwarder_rules.json',
        }
    
    def auto_load(self, config=None):
        """自动加载钩子（按 2026 规范）"""
        if config:
            self.config = config
        
        if not self.config.get('enabled', True):
            return self
        
        if not self.node:
            os_log.err('PORT_FWD', 'NO_NODE', None, {})
            return self
        
        try:
            with self._lock:
                # 劫持 dispatch
                self.original_dispatch = self.node.dispatch
                self.node.dispatch = self._hijacked_dispatch
                self.is_hijacked = True
                self._initialized = True
                reg = get_display_registry()
                reg.unregister('port_forwarder', 'rules')
                reg.register(PortForwarderDisplayProvider(self))
                
                os_log.log_with_const('info', LogMsg.PLUGIN_READY,
                                     plugin='PortForwarder')
        except Exception as exc:
            os_log.err('PORT_FWD', 'LOAD_FAILED', exc, {})
            self._initialized = False
        
        return self
    
    def close(self):
        """清理资源（按 2026 规范）"""
        with self._lock:
            if self._initialized:
                try:
                    # 恢复 dispatch
                    if self.node and self.original_dispatch and self.is_hijacked:
                        self.node.dispatch = self.original_dispatch
                        self.is_hijacked = False
                    
                    # 保存规则
                    self._save_rules_to_file()
                    get_display_registry().unregister('port_forwarder', 'rules')
                    
                    self._initialized = False
                    os_log.log_with_const('info', LogMsg.PLUGIN_CLOSED,
                                         plugin='PortForwarder')
                except Exception as exc:
                    os_log.err('PORT_FWD', 'CLOSE_FAILED', exc, {})
    
    def _load_rules_from_config(self):
        """Load rules from configuration"""
        with self._lock:
            self.rule_sets = {}

            cfg_sets = self.config.get('rule_sets', []) if isinstance(self.config, dict) else []
            if isinstance(cfg_sets, list):
                for item in cfg_sets:
                    try:
                        if isinstance(item, dict):
                            rs = ForwardingRuleSet.from_dict(item)
                            self.rule_sets[rs.name] = rs
                    except Exception as exc:
                        os_log.err('PORT_FWD', 'LOAD_RULESET_CFG', exc, {'item': str(item)[:200]})

            # Persisted file has higher precedence than inline config rule list.
            if bool(self.config.get('persist_rules', True)):
                path = self._rules_file_path()
                payload = read_json(str(path))
                if isinstance(payload, dict):
                    file_sets = payload.get('rule_sets', [])
                    if isinstance(file_sets, list):
                        for item in file_sets:
                            try:
                                if isinstance(item, dict):
                                    rs = ForwardingRuleSet.from_dict(item)
                                    self.rule_sets[rs.name] = rs
                            except Exception as exc:
                                os_log.err('PORT_FWD', 'LOAD_RULESET_FILE', exc, {'item': str(item)[:200]})

            if self.default_rule_set not in self.rule_sets:
                self.rule_sets[self.default_rule_set] = ForwardingRuleSet(
                    name=self.default_rule_set,
                    description='Default forwarding rules',
                    enabled=True,
                    rules=[],
                )

    def _rules_file_path(self) -> Path:
        """Resolve rules persistence path from plugin config."""
        raw = str((self.config or {}).get('rules_file', '') or '').strip()
        if not raw:
            raw = self.get_required_config().get('rules_file', 'data/port_forwarder_rules.json')

        p = Path(raw)
        if p.is_absolute():
            return p
        return Path(ctx.root) / p

    def _save_rules_to_file(self) -> bool:
        """Persist rule sets when persistence is enabled."""
        if not bool((self.config or {}).get('persist_rules', True)):
            return True

        with self._lock:
            path = self._rules_file_path()
            payload = {
                'updated_at': int(time.time()),
                'rule_sets': [rs.to_dict() for rs in self.rule_sets.values()],
            }
            ok = write_json(str(path), payload)
            if not ok:
                os_log.err('PORT_FWD', 'SAVE_RULESET_FILE', RuntimeError('write_json failed'), {'path': str(path)})
            return bool(ok)
    
    # ════════════════════════════════════════════════════════════════════════
    # 3. Core Hijacking Logic
    # ════════════════════════════════════════════════════════════════════════
    
    def _hijacked_dispatch(self, packet: bytes, medium: Optional[str] = None) -> bool:
        """
        Hijacked dispatch method that intercepts and routes packets.
        
        Args:
            packet: Binary packet data
            medium: Original target protocol (e.g., 'UDP')
        
        Returns:
            bool: Success/failure of dispatch
        """
        with self._lock:
            try:
                self.stats['total_packets'] += 1
                
                # Determine target protocol
                target_medium = medium
                applied_rule = None
                
                # Check all rule sets in order
                for rule_set in self.rule_sets.values():
                    if not rule_set.enabled:
                        continue
                    
                    # Check each rule in priority order
                    for rule in rule_set.get_rules_sorted():
                        if self._matches_rule(packet, medium, rule):
                            target_medium = rule.to_protocol
                            applied_rule = rule
                            
                            # Update target in config if needed
                            self._update_transport_config(rule)
                            
                            # Track statistics
                            rule_key = f"{rule.from_protocol}→{rule.to_protocol}"
                            self.stats['rules_applied'][rule_key] = \
                                self.stats['rules_applied'].get(rule_key, 0) + 1
                            
                            os_log.info('PORT_FWD', 'RULE_APPLIED', f'Applied rule: {rule_key} → {rule.to_host}:{rule.to_port}', {'rule': rule_key, 'to_host': rule.to_host, 'to_port': rule.to_port})
                            break
                
                # Dispatch using original method
                success = self.original_dispatch(packet, medium=target_medium)
                
                if success:
                    if applied_rule:
                        self.stats['forwarded_packets'] += 1
                    else:
                        self.stats['original_packets'] += 1
                else:
                    self.stats['failed_forwards'] += 1
                
                return success
            
            except Exception as exc:
                os_log.err('PORT_FWD', 'HIJACKED_DISPATCH', exc, {'medium': medium})
                # Fallback: use original dispatch
                return self.original_dispatch(packet, medium=medium)
    
    def _matches_rule(self, packet: bytes, medium: Optional[str], rule: ForwardingRule) -> bool:
        """
        Check if a packet matches a forwarding rule.
        
        Args:
            packet: Binary packet data
            medium: Current protocol
            rule: ForwardingRule to check
        
        Returns:
            bool: Whether packet matches the rule
        """
        try:
            # Match source protocol
            if medium and medium.upper() != rule.from_protocol:
                return False
            
            # Match source port (if specified)
            if rule.from_port is not None:
                # Try to extract destination port from packet
                packet_port = self._extract_dest_port(packet)
                if packet_port and packet_port != rule.from_port:
                    return False
            
            # Custom condition (placeholder for advanced filtering)
            # In production, could use eval() with restricted namespace
            if rule.condition:
                # TODO: Implement custom condition evaluation
                pass
            
            return True
        except Exception:
            return False
    
    def _extract_dest_port(self, packet: bytes) -> Optional[int]:
        """
        Extract destination port from packet (if applicable).
        
        Note: This is a simplified version. Real implementation would need
        to understand the packet structure better.
        
        Args:
            packet: Binary packet data
        
        Returns:
            Optional[int]: Destination port if detectable, None otherwise
        """
        try:
            # Simplified: assume port info is in bytes 6-8
            if len(packet) >= 8:
                return int.from_bytes(packet[6:8], byteorder='big')
            return None
        except Exception:
            return None
    
    def _update_transport_config(self, rule: ForwardingRule):
        """
        Update node's transport configuration based on rule.
        
        Args:
            rule: ForwardingRule with target configuration
        """
        if not self.node or not hasattr(self.node, 'config'):
            return
        
        try:
            # Update transport-specific config
            protocol = rule.to_protocol.lower()
            
            if 'RESOURCES' not in self.node.config:
                self.node.config['RESOURCES'] = {}
            
            # For IP-based protocols (TCP, UDP, MQTT, etc)
            if protocol in ['tcp', 'udp']:
                if 'transport_config' not in self.node.config['RESOURCES']:
                    self.node.config['RESOURCES']['transport_config'] = {}
                
                self.node.config['RESOURCES']['transport_config'][protocol] = {
                    'host': rule.to_host,
                    'port': rule.to_port,
                }
            
            elif protocol in ['mqtt', 'matter', 'zigbee']:
                if 'application_config' not in self.node.config['RESOURCES']:
                    self.node.config['RESOURCES']['application_config'] = {}
                
                self.node.config['RESOURCES']['application_config'][protocol] = {
                    'host': rule.to_host,
                    'port': rule.to_port,
                }
            
            elif protocol in ['uart', 'rs485', 'can', 'lora', 'bluetooth']:
                if 'physical_config' not in self.node.config['RESOURCES']:
                    self.node.config['RESOURCES']['physical_config'] = {}
                
                self.node.config['RESOURCES']['physical_config'][protocol] = {
                    'port': rule.to_port,
                    'host': rule.to_host,  # May not apply for serial
                }
        except Exception as exc:
            os_log.err('PORT_FWD', 'UPDATE_CONFIG', exc, {'rule': rule})
    
    # ════════════════════════════════════════════════════════════════════════
    # 4. Rule Management API
    # ════════════════════════════════════════════════════════════════════════
    
    def add_rule_set(self, rule_set: ForwardingRuleSet):
        """Add a new rule set"""
        with self._lock:
            self.rule_sets[rule_set.name] = rule_set
            self._save_rules_to_file()
    
    def remove_rule_set(self, name: str):
        """Remove a rule set"""
        with self._lock:
            if name in self.rule_sets:
                del self.rule_sets[name]
                self._save_rules_to_file()
    
    def get_rule_set(self, name: str) -> Optional[ForwardingRuleSet]:
        """Get a rule set by name"""
        with self._lock:
            return self.rule_sets.get(name)
    
    def list_rules(self, rule_set_name: Optional[str] = None) -> List[Dict]:
        """List all rules, optionally filtered by rule set"""
        with self._lock:
            rules = []
            
            for rs_name, rs in self.rule_sets.items():
                if rule_set_name and rs_name != rule_set_name:
                    continue
                
                for rule in rs.rules:
                    rules.append({
                        'rule_set': rs_name,
                        'rule': rule.to_dict(),
                    })
            
            return rules
    
    def get_stats(self) -> dict:
        """Get forwarding statistics"""
        with self._lock:
            return dict(self.stats)
    
    # ════════════════════════════════════════════════════════════════════════
    # 5. CLI Commands
    # ════════════════════════════════════════════════════════════════════════
    
    def get_cli_commands(self) -> dict:
        """Expose CLI commands"""
        return {
            'status': self.handle_status,
            'list': self.handle_list,
            'add-rule': self.handle_add_rule,
            'remove-rule': self.handle_remove_rule,
            'stats': self.handle_stats,
        }
    
    def get_cli_completions(self) -> dict:
        """CLI command completions"""
        return {
            'status': 'Show forwarding status and rule sets',
            'list': 'List all active forwarding rules',
            'add-rule': 'Add a new forwarding rule',
            'remove-rule': 'Remove a forwarding rule',
            'stats': 'Show forwarding statistics',
        }
    
    def handle_status(self, args, **kwargs) -> dict:
        """Handle 'status' command"""
        with self._lock:
            return {
                'hijacked': self.is_hijacked,
                'rule_sets': list(self.rule_sets.keys()),
                'total_rules': sum(len(rs.rules) for rs in self.rule_sets.values()),
                'stats': self.stats,
            }
    
    def handle_list(self, args, **kwargs) -> dict:
        """Handle 'list' command"""
        with self._lock:
            return {
                'rules': self.list_rules(),
                'total': sum(len(rs.rules) for rs in self.rule_sets.values()),
            }
    
    def handle_add_rule(self, args, **kwargs) -> dict:
        """Handle 'add-rule' command"""
        try:
            from_proto = getattr(args, 'from_protocol', 'UDP')
            to_proto = getattr(args, 'to_protocol', 'TCP')
            to_host = getattr(args, 'to_host', '127.0.0.1')
            to_port = int(getattr(args, 'to_port', 8080))
            rule_set_name = getattr(args, 'rule_set', 'default')
            
            # Get or create rule set
            if rule_set_name not in self.rule_sets:
                self.rule_sets[rule_set_name] = ForwardingRuleSet(
                    name=rule_set_name,
                    rules=[]
                )
            
            # Create and add rule
            rule = ForwardingRule(
                from_protocol=from_proto,
                to_protocol=to_proto,
                to_host=to_host,
                to_port=to_port,
            )
            
            self.rule_sets[rule_set_name].add_rule(rule)
            self._save_rules_to_file()
            
            return {
                'status': 'ok',
                'message': f'Added rule: {from_proto}→{to_proto} to {to_host}:{to_port}',
            }
        except Exception as exc:
            return {
                'status': 'error',
                'message': str(exc),
            }
    
    def handle_remove_rule(self, args, **kwargs) -> dict:
        """Handle 'remove-rule' command"""
        try:
            rule_set_name = getattr(args, 'rule_set', 'default')
            rule_index = int(getattr(args, 'index', 0))
            
            if rule_set_name not in self.rule_sets:
                return {'status': 'error', 'message': f'Rule set not found: {rule_set_name}'}
            
            rs = self.rule_sets[rule_set_name]
            if rule_index < 0 or rule_index >= len(rs.rules):
                return {'status': 'error', 'message': f'Invalid rule index: {rule_index}'}
            
            removed = rs.rules.pop(rule_index)
            self._save_rules_to_file()
            
            return {
                'status': 'ok',
                'message': f'Removed rule: {removed.from_protocol}→{removed.to_protocol}',
            }
        except Exception as exc:
            return {
                'status': 'error',
                'message': str(exc),
            }
    
    def handle_stats(self, args, **kwargs) -> dict:
        """Handle 'stats' command"""
        return {
            'statistics': self.get_stats(),
        }

