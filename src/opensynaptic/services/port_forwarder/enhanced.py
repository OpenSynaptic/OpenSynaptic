"""
Enhanced Port Forwarder – Complete Network Management Platform

Combines:
- Middleware (钩子和拦截器)
- Proxy (代理转发)
- Firewall (防火墙规则)
- Protocol Converter (协议转换)
- Traffic Shaper (流量整形)

Architecture:
    PortForwarder
    ├── ForwardingRule (转发规则)
    ├── FirewallRule (防火墙规则)
    ├── ProtocolConverter (协议转换)
    ├── TrafficShaper (流量整形)
    ├── Middleware (中间件)
    └── Proxy (代理)
"""

import threading
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from collections import deque

from opensynaptic.utils import os_log, read_json, write_json, ctx


# ════════════════════════════════════════════════════════════════════════════
# 1. 防火墙规则 (Firewall Rules)
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class FirewallRule:
    """
    防火墙规则 - 控制数据包的允许/拒绝
    
    支持：
    - 协议过滤
    - 源 IP/端口范围
    - 目标 IP/端口范围
    - 大小限制
    - 速率限制
    - 自定义条件
    """
    
    name: str
    action: str  # 'allow' 或 'deny'
    from_protocol: Optional[str] = None
    from_ip: Optional[str] = None
    from_port_range: Optional[tuple] = None  # (min, max)
    to_ip: Optional[str] = None
    to_port_range: Optional[tuple] = None
    packet_size_min: Optional[int] = None
    packet_size_max: Optional[int] = None
    enabled: bool = True
    priority: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def matches(self, packet: bytes, from_proto: str, from_ip: str = None, 
                from_port: int = None, to_port: int = None) -> bool:
        """检查数据包是否匹配此规则"""
        # 协议匹配
        if self.from_protocol and from_proto.upper() != self.from_protocol.upper():
            return False
        
        # 源 IP 匹配
        if self.from_ip and from_ip != self.from_ip:
            return False
        
        # 源端口范围匹配
        if self.from_port_range and from_port:
            min_port, max_port = self.from_port_range
            if not (min_port <= from_port <= max_port):
                return False
        
        # 目标端口范围匹配
        if self.to_port_range and to_port:
            min_port, max_port = self.to_port_range
            if not (min_port <= to_port <= max_port):
                return False
        
        # 数据包大小匹配
        packet_len = len(packet)
        if self.packet_size_min and packet_len < self.packet_size_min:
            return False
        if self.packet_size_max and packet_len > self.packet_size_max:
            return False
        
        return True


# ════════════════════════════════════════════════════════════════════════════
# 2. 流量整形器 (Traffic Shaper)
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class TrafficShaper:
    """
    流量整形 - 控制转发速率
    
    支持：
    - 速率限制（每秒字节数）
    - 突发容量
    - 时间窗口
    - 令牌桶算法
    """
    
    name: str
    rate_limit_bps: int  # 字节/秒
    burst_capacity: int  # 最大突发字节数
    enabled: bool = True
    
    def __post_init__(self):
        """初始化令牌桶"""
        self.tokens = self.burst_capacity
        self.last_refill = time.time()
        self._lock = threading.Lock()
    
    def can_send(self, packet_size: int) -> bool:
        """检查是否可以发送数据包"""
        with self._lock:
            now = time.time()
            elapsed = now - self.last_refill
            
            # 补充令牌
            tokens_to_add = elapsed * self.rate_limit_bps
            self.tokens = min(self.burst_capacity, self.tokens + tokens_to_add)
            self.last_refill = now
            
            # 检查是否有足够的令牌
            if self.tokens >= packet_size:
                self.tokens -= packet_size
                return True
            
            return False
    
    def get_wait_time(self, packet_size: int) -> float:
        """获取需要等待的时间（秒）"""
        with self._lock:
            if self.tokens >= packet_size:
                return 0.0
            
            deficit = packet_size - self.tokens
            return deficit / self.rate_limit_bps


# ════════════════════════════════════════════════════════════════════════════
# 3. 协议转换器 (Protocol Converter)
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ProtocolConverter:
    """
    协议转换 - 转换协议格式
    
    支持：
    - 协议映射（UDP ↔ TCP）
    - 报头转换
    - 编码转换
    - 自定义转换函数
    """
    
    name: str
    from_protocol: str
    to_protocol: str
    transform_func: Optional[Callable] = None  # 自定义转换函数
    enabled: bool = True
    
    def convert(self, packet: bytes) -> bytes:
        """转换数据包"""
        if self.transform_func:
            return self.transform_func(packet)
        
        # 默认转换：只改变协议标记
        return packet


# ════════════════════════════════════════════════════════════════════════════
# 4. 中间件 (Middleware)
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class Middleware:
    """
    中间件 - 在转发前后执行钩子
    
    支持：
    - 前置钩子（before_dispatch）
    - 后置钩子（after_dispatch）
    - 日志、监控、修改包内容
    """
    
    name: str
    before_dispatch: Optional[Callable] = None  # (packet, medium) -> packet
    after_dispatch: Optional[Callable] = None   # (packet, medium, result) -> result
    enabled: bool = True
    
    def execute_before(self, packet: bytes, medium: str) -> bytes:
        """执行前置钩子"""
        if self.enabled and self.before_dispatch:
            return self.before_dispatch(packet, medium)
        return packet
    
    def execute_after(self, packet: bytes, medium: str, result: bool) -> bool:
        """执行后置钩子"""
        if self.enabled and self.after_dispatch:
            return self.after_dispatch(packet, medium, result)
        return result


# ════════════════════════════════════════════════════════════════════════════
# 5. 代理 (Proxy)
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ProxyRule:
    """
    代理规则 - 完全代理转发
    
    支持：
    - 请求/响应拦截
    - 头部修改
    - 缓存
    - 负载均衡
    """
    
    name: str
    from_protocol: str
    to_protocol: str
    to_host: str
    to_port: int
    
    # 代理选项
    cache_enabled: bool = False
    cache_ttl: int = 300  # 秒
    load_balance_enabled: bool = False
    backup_hosts: List[str] = field(default_factory=list)
    
    # 统计
    request_count: int = 0
    response_count: int = 0
    error_count: int = 0
    
    def __post_init__(self):
        self._lock = threading.Lock()
        self._cache: Dict[bytes, tuple] = {}  # {packet: (response, timestamp)}


# ════════════════════════════════════════════════════════════════════════════
# 6. 增强的 Port Forwarder
# ════════════════════════════════════════════════════════════════════════════

class EnhancedPortForwarder:
    """
    增强的端口转发器 - 完整的网络管理平台
    
    集成功能：
    1. 中间件 (Middleware) - 钩子系统
    2. 代理 (Proxy) - 完全代理转发
    3. 防火墙 (Firewall) - 数据包过滤
    4. 协议转换器 (Protocol Converter) - 协议转换
    5. 流量整形器 (Traffic Shaper) - 速率控制
    
    所有功能都可以动态启用/禁用
    """
    
    def __init__(self, node=None, **kwargs):
        """
        初始化增强的端口转发器
        
        Args:
            node: OpenSynaptic 节点
            **kwargs: 配置参数，包括：
                firewall_enabled: bool (默认 True)
                traffic_shaping_enabled: bool (默认 True)
                protocol_conversion_enabled: bool (默认 True)
                middleware_enabled: bool (默认 True)
                proxy_enabled: bool (默认 True)
        """
        self.node = node
        self.config = kwargs or {}
        self._lock = threading.RLock()
        
        # 功能开关（可动态修改）
        self.features_enabled = {
            'firewall': self.config.get('firewall_enabled', True),
            'traffic_shaping': self.config.get('traffic_shaping_enabled', True),
            'protocol_conversion': self.config.get('protocol_conversion_enabled', True),
            'middleware': self.config.get('middleware_enabled', True),
            'proxy': self.config.get('proxy_enabled', True),
        }
        
        # 各个功能组件
        self.firewall_rules: List[FirewallRule] = []
        self.traffic_shapers: Dict[str, TrafficShaper] = {}
        self.protocol_converters: Dict[str, ProtocolConverter] = {}
        self.middlewares: List[Middleware] = []
        self.proxy_rules: Dict[str, ProxyRule] = {}
        
        # 统计
        self.stats = {
            'total_packets': 0,
            'allowed_packets': 0,
            'denied_packets': 0,
            'converted_packets': 0,
            'proxied_packets': 0,
            'shaped_packets': 0,
            'middleware_executed': 0,
            'features_enabled': dict(self.features_enabled),
        }
        
        # 原始方法备份
        self.original_dispatch = None
        self.is_hijacked = False
    
    @staticmethod
    def get_required_config() -> dict:
        """返回默认配置"""
        return {
            'enabled': True,
            'mode': 'auto',
            'firewall_enabled': True,
            'traffic_shaping_enabled': True,
            'protocol_conversion_enabled': True,
            'middleware_enabled': True,
            'proxy_enabled': True,
        }
    
    # ════════════════════════════════════════════════════════════════════════
    # 功能开关接口 (Feature Toggle Interface)
    # ════════════════════════════════════════════════════════════════════════
    
    def enable_feature(self, feature: str) -> bool:
        """启用指定功能"""
        with self._lock:
            if feature in self.features_enabled:
                self.features_enabled[feature] = True
                self.stats['features_enabled'][feature] = True
                os_log.info('ENHANCED_PF', 'FEATURE_ENABLE', f'Enabled feature: {feature}', {'feature': feature})
                return True
            return False
    
    def disable_feature(self, feature: str) -> bool:
        """禁用指定功能"""
        with self._lock:
            if feature in self.features_enabled:
                self.features_enabled[feature] = False
                self.stats['features_enabled'][feature] = False
                os_log.info('ENHANCED_PF', 'FEATURE_DISABLE', f'Disabled feature: {feature}', {'feature': feature})
                return True
            return False
    
    def toggle_feature(self, feature: str) -> bool:
        """切换指定功能的启用状态"""
        with self._lock:
            if feature in self.features_enabled:
                self.features_enabled[feature] = not self.features_enabled[feature]
                self.stats['features_enabled'][feature] = self.features_enabled[feature]
                status = 'enabled' if self.features_enabled[feature] else 'disabled'
                os_log.info('ENHANCED_PF', 'FEATURE_TOGGLE', f'Toggled feature {feature}: {status}', {'feature': feature, 'status': status})
                return self.features_enabled[feature]
            return False
    
    def get_feature_status(self) -> dict:
        """获取所有功能的启用状态"""
        with self._lock:
            return dict(self.features_enabled)
    
    def set_features(self, **kwargs) -> dict:
        """批量设置功能启用状态"""
        with self._lock:
            for feature, enabled in kwargs.items():
                if feature in self.features_enabled:
                    self.features_enabled[feature] = bool(enabled)
                    self.stats['features_enabled'][feature] = bool(enabled)
            
            os_log.info('ENHANCED_PF', 'FEATURE_SET', f'Set features: {kwargs}', {'features': kwargs})
            return dict(self.features_enabled)
    
    # ════════════════════════════════════════════════════════════════════════
    # 防火墙接口 (Firewall Interface)
    # ════════════════════════════════════════════════════════════════════════
    
    def add_firewall_rule(self, rule: FirewallRule):
        """添加防火墙规则"""
        with self._lock:
            self.firewall_rules.append(rule)
            # 按优先级排序
            self.firewall_rules.sort(key=lambda r: r.priority, reverse=True)
    
    def check_firewall(self, packet: bytes, medium: str) -> bool:
        """检查防火墙 - 返回 True 如果允许"""
        if not self.features_enabled.get('firewall', True):
            return True
        
        with self._lock:
            for rule in self.firewall_rules:
                if not rule.enabled:
                    continue
                
                if rule.matches(packet, medium):
                    if rule.action == 'deny':
                        os_log.info('ENHANCED_PF', 'FIREWALL_BLOCK', f'Firewall blocked: {rule.name}', {'rule': rule.name})
                        self.stats['denied_packets'] += 1
                        return False
                    elif rule.action == 'allow':
                        self.stats['allowed_packets'] += 1
                        return True
        
        # 默认允许
        return True
    
    # ════════════════════════════════════════════════════════════════════════
    # 流量整形接口 (Traffic Shaper Interface)
    # ════════════════════════════════════════════════════════════════════════
    
    def add_traffic_shaper(self, name: str, shaper: TrafficShaper):
        """添加流量整形器"""
        with self._lock:
            self.traffic_shapers[name] = shaper
    
    def apply_traffic_shaping(self, packet: bytes, shaper_name: str) -> float:
        """应用流量整形 - 返回需要等待的秒数"""
        if not self.features_enabled.get('traffic_shaping', True):
            return 0.0
        
        with self._lock:
            shaper = self.traffic_shapers.get(shaper_name)
            if not shaper or not shaper.enabled:
                return 0.0
            
            if shaper.can_send(len(packet)):
                self.stats['shaped_packets'] += 1
                return 0.0
            
            return shaper.get_wait_time(len(packet))
    
    # ════════════════════════════════════════════════════════════════════════
    # 协议转换接口 (Protocol Converter Interface)
    # ════════════════════════════════════════════════════════════════════════
    
    def add_protocol_converter(self, converter: ProtocolConverter):
        """添加协议转换器"""
        with self._lock:
            key = f"{converter.from_protocol}→{converter.to_protocol}"
            self.protocol_converters[key] = converter
    
    def convert_protocol(self, packet: bytes, from_proto: str, to_proto: str) -> bytes:
        """转换协议"""
        if not self.features_enabled.get('protocol_conversion', True):
            return packet
        
        with self._lock:
            key = f"{from_proto}→{to_proto}"
            converter = self.protocol_converters.get(key)
            if converter and converter.enabled:
                self.stats['converted_packets'] += 1
                return converter.convert(packet)
        
        return packet
    
    # ════════════════════════════════════════════════════════════════════════
    # 中间件接口 (Middleware Interface)
    # ════════════════════════════════════════════════════════════════════════
    
    def add_middleware(self, middleware: Middleware):
        """添加中间件"""
        with self._lock:
            self.middlewares.append(middleware)
    
    def execute_middlewares_before(self, packet: bytes, medium: str) -> bytes:
        """执行所有前置中间件"""
        if not self.features_enabled.get('middleware', True):
            return packet
        
        with self._lock:
            for middleware in self.middlewares:
                packet = middleware.execute_before(packet, medium)
                self.stats['middleware_executed'] += 1
        
        return packet
    
    def execute_middlewares_after(self, packet: bytes, medium: str, result: bool) -> bool:
        """执行所有后置中间件"""
        if not self.features_enabled.get('middleware', True):
            return result
        
        with self._lock:
            for middleware in self.middlewares:
                result = middleware.execute_after(packet, medium, result)
        
        return result
    
    # ════════════════════════════════════════════════════════════════════════
    # 代理接口 (Proxy Interface)
    # ════════════════════════════════════════════════════════════════════════
    
    def add_proxy_rule(self, rule: ProxyRule):
        """添加代理规则"""
        with self._lock:
            self.proxy_rules[rule.name] = rule
    
    def apply_proxy(self, packet: bytes, rule_name: str) -> tuple:
        """应用代理规则 - 返回 (packet, result)"""
        if not self.features_enabled.get('proxy', True):
            return packet, True
        
        with self._lock:
            proxy = self.proxy_rules.get(rule_name)
            if not proxy:
                return packet, True
            
            # 检查缓存
            if proxy.cache_enabled and packet in proxy._cache:
                response, timestamp = proxy._cache[packet]
                if time.time() - timestamp < proxy.cache_ttl:
                    self.stats['proxied_packets'] += 1
                    return response, True
            
            # 执行代理
            # （实际实现会转发到目标并获取响应）
            response = packet  # 占位符
            
            # 缓存响应
            if proxy.cache_enabled:
                proxy._cache[packet] = (response, time.time())
            
            proxy.request_count += 1
            self.stats['proxied_packets'] += 1
            
            return response, True
    
    # ════════════════════════════════════════════════════════════════════════
    # 核心劫持逻辑 (Core Hijacking Logic)
    # ════════════════════════════════════════════════════════════════════════
    
    def auto_load(self):
        """初始化 - 劫持 dispatch 方法"""
        if not self.node:
            raise RuntimeError('EnhancedPortForwarder requires node instance')
        
        try:
            self.original_dispatch = self.node.dispatch
            self.node.dispatch = self._hijacked_dispatch
            self.is_hijacked = True
            
            os_log.info('ENHANCED_PF', 'AUTO_LOAD', 'Enhanced Port Forwarder hijacked dispatch')
            return self
        except Exception as exc:
            os_log.err('ENHANCED_PF', 'AUTO_LOAD', exc, {})
            raise
    
    def close(self):
        """关闭 - 恢复原始 dispatch"""
        try:
            if self.node and self.original_dispatch and self.is_hijacked:
                self.node.dispatch = self.original_dispatch
                self.is_hijacked = False
            
            os_log.info('ENHANCED_PF', 'CLOSE', f'Enhanced Port Forwarder closed, stats: {self.stats}', {'stats': self.stats})
        except Exception as exc:
            os_log.err('ENHANCED_PF', 'CLOSE', exc, {})
    
    def _hijacked_dispatch(self, packet: bytes, medium: Optional[str] = None) -> bool:
        """
        劫持的 dispatch 方法 - 完整的处理流程：
        1. 中间件前置
        2. 防火墙检查
        3. 流量整形
        4. 协议转换
        5. 代理
        6. 原始 dispatch
        7. 中间件后置
        """
        with self._lock:
            self.stats['total_packets'] += 1
            
            try:
                # 1. 执行前置中间件
                packet = self.execute_middlewares_before(packet, medium)
                
                # 2. 防火墙检查
                if not self.check_firewall(packet, medium):
                    return False
                
                # 3. 流量整形
                wait_time = self.apply_traffic_shaping(packet, medium or 'default')
                if wait_time > 0:
                    time.sleep(wait_time)
                
                # 4. 协议转换
                packet = self.convert_protocol(packet, medium, medium)
                
                # 5. 代理（可选）
                if medium in self.proxy_rules:
                    packet, _ = self.apply_proxy(packet, medium)
                
                # 6. 原始 dispatch
                success = self.original_dispatch(packet, medium=medium)
                
                # 7. 执行后置中间件
                success = self.execute_middlewares_after(packet, medium, success)
                
                return success
            
            except Exception as exc:
                os_log.err('ENHANCED_PF', 'HIJACKED_DISPATCH', exc, {'medium': medium})
                return self.original_dispatch(packet, medium=medium)
    
    def get_stats(self) -> dict:
        """获取统计数据"""
        with self._lock:
            return dict(self.stats)
    
    def get_cli_commands(self) -> dict:
        """暴露 CLI 命令"""
        return {
            'status': self.handle_status,
            'features': self.handle_features,
            'enable': self.handle_enable,
            'disable': self.handle_disable,
            'toggle': self.handle_toggle,
            'firewall-list': self.handle_firewall_list,
            'firewall-add': self.handle_firewall_add,
            'stats': self.handle_stats,
        }
    
    def get_cli_completions(self) -> dict:
        """CLI 命令补全"""
        return {
            'status': 'Show enhanced port forwarder status',
            'features': 'Show all features and their status',
            'enable': 'Enable a feature (firewall/traffic_shaping/protocol_conversion/middleware/proxy)',
            'disable': 'Disable a feature',
            'toggle': 'Toggle a feature on/off',
            'firewall-list': 'List firewall rules',
            'firewall-add': 'Add firewall rule',
            'stats': 'Show statistics',
        }
    
    def handle_status(self, args, **kwargs) -> dict:
        """处理 status 命令"""
        with self._lock:
            return {
                'hijacked': self.is_hijacked,
                'features': self.features_enabled,
                'firewall_rules': len(self.firewall_rules),
                'traffic_shapers': len(self.traffic_shapers),
                'protocol_converters': len(self.protocol_converters),
                'middlewares': len(self.middlewares),
                'proxy_rules': len(self.proxy_rules),
                'stats': self.stats,
            }
    
    def handle_features(self, args, **kwargs) -> dict:
        """处理 features 命令 - 显示所有功能状态"""
        with self._lock:
            features = {}
            for name, enabled in self.features_enabled.items():
                features[name] = {
                    'enabled': enabled,
                    'status': '✅ enabled' if enabled else '❌ disabled'
                }
            return {'features': features}
    
    def handle_enable(self, args, **kwargs) -> dict:
        """处理 enable 命令"""
        try:
            feature = getattr(args, 'feature', None)
            if not feature:
                return {'status': 'error', 'message': 'feature name required'}
            
            if self.enable_feature(feature):
                return {'status': 'ok', 'message': f'Enabled feature: {feature}'}
            else:
                return {'status': 'error', 'message': f'Unknown feature: {feature}'}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}
    
    def handle_disable(self, args, **kwargs) -> dict:
        """处理 disable 命令"""
        try:
            feature = getattr(args, 'feature', None)
            if not feature:
                return {'status': 'error', 'message': 'feature name required'}
            
            if self.disable_feature(feature):
                return {'status': 'ok', 'message': f'Disabled feature: {feature}'}
            else:
                return {'status': 'error', 'message': f'Unknown feature: {feature}'}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}
    
    def handle_toggle(self, args, **kwargs) -> dict:
        """处理 toggle 命令"""
        try:
            feature = getattr(args, 'feature', None)
            if not feature:
                return {'status': 'error', 'message': 'feature name required'}
            
            new_status = self.toggle_feature(feature)
            if new_status is not False:
                status_str = 'enabled' if new_status else 'disabled'
                return {'status': 'ok', 'message': f'Feature {feature} is now {status_str}'}
            else:
                return {'status': 'error', 'message': f'Unknown feature: {feature}'}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}
    
    def handle_firewall_list(self, args, **kwargs) -> dict:
        """处理 firewall-list 命令"""
        with self._lock:
            rules = [
                {
                    'name': r.name,
                    'action': r.action,
                    'from_protocol': r.from_protocol,
                    'priority': r.priority,
                    'enabled': r.enabled,
                }
                for r in self.firewall_rules
            ]
            return {'rules': rules, 'total': len(rules)}
    
    def handle_firewall_add(self, args, **kwargs) -> dict:
        """处理 firewall-add 命令"""
        try:
            name = getattr(args, 'name', 'rule')
            action = getattr(args, 'action', 'allow')
            from_protocol = getattr(args, 'from_protocol', None)
            
            rule = FirewallRule(
                name=name,
                action=action,
                from_protocol=from_protocol,
            )
            self.add_firewall_rule(rule)
            
            return {'status': 'ok', 'message': f'Added firewall rule: {name}'}
        except Exception as exc:
            return {'status': 'error', 'message': str(exc)}
    
    def handle_stats(self, args, **kwargs) -> dict:
        """处理 stats 命令"""
        return {'statistics': self.get_stats()}

