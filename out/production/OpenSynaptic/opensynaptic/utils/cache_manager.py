"""
OpenSynaptic Registry Cache LRU Implementation
===============================================

替换 OSVisualFusionEngine 中的无限制 _RAM_CACHE，
使用 TTL + LRU 限制的缓存管理器。

使用示例:
    cache = RegistryCache(max_size=1000, ttl_seconds=3600)
    registry = cache.get('aid_12345', lambda: load_registry_from_disk('aid_12345'))
"""

import time
import threading
from collections import OrderedDict
from typing import Callable, Any, Optional


class RegistryCache:
    """
    线程安全的 LRU 缓存，带自动 TTL 驱逐。
    
    特性:
    - 最大大小限制（防止内存泄漏）
    - TTL 过期驱逐
    - LRU 替换策略
    - 线程安全（RLock）
    - 性能监控（命中率、驱逐计数）
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        """
        初始化缓存。
        
        Args:
            max_size: 最大条目数（达到时触发 LRU 驱逐）
            ttl_seconds: TTL 秒数（超过则标记为过期）
        """
        self.max_size = max_size
        self.ttl = ttl_seconds
        self.cache = OrderedDict()  # 保存 value
        self.metadata = {}  # key -> {'timestamp': float, 'access_count': int}
        self.lock = threading.RLock()
        
        # 监控指标
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expirations': 0,
        }
    
    def _is_expired(self, key: str) -> bool:
        """检查条目是否已过期。"""
        if key not in self.metadata:
            return False
        age = time.time() - self.metadata[key]['timestamp']
        return age > self.ttl
    
    def _evict_lru(self) -> Optional[str]:
        """驱逐最少使用的条目（基于访问时间）。"""
        if not self.cache:
            return None
        
        # 找到访问时间最早的条目
        oldest_key = min(
            self.cache.keys(),
            key=lambda k: self.metadata.get(k, {}).get('timestamp', float('inf'))
        )
        
        if oldest_key in self.cache:
            del self.cache[oldest_key]
        if oldest_key in self.metadata:
            del self.metadata[oldest_key]
        
        self.stats['evictions'] += 1
        return oldest_key
    
    def _cleanup_expired(self) -> int:
        """扫描并清理所有过期条目。返回清理数量。"""
        expired_keys = [k for k in self.cache.keys() if self._is_expired(k)]
        
        for k in expired_keys:
            del self.cache[k]
            if k in self.metadata:
                del self.metadata[k]
            self.stats['expirations'] += 1
        
        return len(expired_keys)
    
    def get(self, key: str, loader_fn: Callable[[], Any]) -> Any:
        """
        获取缓存条目，如不存在则调用 loader_fn 加载。
        
        Args:
            key: 缓存键
            loader_fn: 加载函数（返回值将被缓存）
        
        Returns:
            缓存值或新加载的值
        """
        with self.lock:
            # 检查是否存在且未过期
            if key in self.cache and not self._is_expired(key):
                self.stats['hits'] += 1
                self.metadata[key]['timestamp'] = time.time()
                return self.cache[key]
            
            # 缓存未命中
            self.stats['misses'] += 1
            
            # 如果满容量，触发 LRU 驱逐
            while len(self.cache) >= self.max_size:
                self._evict_lru()
            
            # 加载新值
            value = loader_fn()
            self.cache[key] = value
            self.metadata[key] = {
                'timestamp': time.time(),
                'access_count': 1
            }
            
            return value
    
    def put(self, key: str, value: Any) -> None:
        """直接放入缓存值（用于主动更新）。"""
        with self.lock:
            if len(self.cache) >= self.max_size and key not in self.cache:
                self._evict_lru()
            
            self.cache[key] = value
            self.metadata[key] = {
                'timestamp': time.time(),
                'access_count': 0
            }
    
    def invalidate(self, key: str) -> bool:
        """手动失效指定键。"""
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                if key in self.metadata:
                    del self.metadata[key]
                return True
            return False
    
    def clear(self) -> None:
        """清空所有缓存。"""
        with self.lock:
            self.cache.clear()
            self.metadata.clear()
    
    def size(self) -> int:
        """获取当前缓存大小。"""
        with self.lock:
            return len(self.cache)
    
    def get_stats(self) -> dict:
        """获取性能统计。"""
        with self.lock:
            total_access = self.stats['hits'] + self.stats['misses']
            hit_rate = (
                self.stats['hits'] / total_access * 100
                if total_access > 0 else 0
            )
            
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self.stats['hits'],
                'misses': self.stats['misses'],
                'hit_rate_%': hit_rate,
                'evictions': self.stats['evictions'],
                'expirations': self.stats['expirations'],
            }
    
    def periodic_cleanup(self, min_interval: float = 60.0) -> int:
        """
        定期清理过期条目（应从后台线程调用）。
        
        Args:
            min_interval: 两次清理之间的最小间隔（秒）
        
        Returns:
            本次清理的条目数
        """
        # 这可由上层线程池管理调用
        return self._cleanup_expired()


class SessionCache:
    """
    专门用于 OSHandshakeManager 的会话缓存。
    自动清理过期会话。
    """
    
    def __init__(self, ttl_seconds: int = 3600, cleanup_interval: int = 300):
        """
        Args:
            ttl_seconds: 会话 TTL
            cleanup_interval: 清理间隔（秒）
        """
        self.sessions = {}
        self.ttl = ttl_seconds
        self.cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()
        self.lock = threading.RLock()
    
    def _auto_cleanup(self):
        """检查是否需要清理，如需要则清理。"""
        now = time.time()
        if now - self._last_cleanup < self.cleanup_interval:
            return 0
        
        expired_keys = [
            k for k, v in self.sessions.items()
            if now - v.get('last', now) > self.ttl
        ]
        
        for k in expired_keys:
            del self.sessions[k]
        
        self._last_cleanup = now
        return len(expired_keys)
    
    def get(self, aid, create_fn=None):
        """获取或创建会话。"""
        with self.lock:
            self._auto_cleanup()
            
            if aid in self.sessions:
                self.sessions[aid]['last'] = time.time()
                return self.sessions[aid]
            
            if create_fn:
                session = create_fn()
                self.sessions[aid] = session
                return session
            
            return None
    
    def put(self, aid, session_data):
        """存储会话。"""
        with self.lock:
            session_data['last'] = time.time()
            self.sessions[aid] = session_data
    
    def clear_expired(self):
        """手动清理所有过期会话。"""
        with self.lock:
            return self._auto_cleanup()
    
    def size(self):
        """获取当前会话数。"""
        with self.lock:
            return len(self.sessions)


# ============================================================================
# 集成示例
# ============================================================================

if __name__ == '__main__':
    # 演示 RegistryCache
    print("=== RegistryCache Demo ===")
    cache = RegistryCache(max_size=5, ttl_seconds=2)
    
    def load_data(key):
        print(f"  [Loading] {key}")
        return {'data': f'content_{key}'}
    
    # 加载 5 个条目
    for i in range(5):
        val = cache.get(f'key_{i}', lambda i=i: load_data(f'key_{i}'))
        print(f"Got: {val}")
    
    # 再加载 1 个（应触发 LRU 驱逐）
    val = cache.get('key_5', lambda: load_data('key_5'))
    print(f"Got (should evict LRU): {val}")
    
    # 打印统计
    print(f"\nStats: {cache.get_stats()}")
    
    # 等待 TTL 过期
    print("\nWaiting 3 seconds for TTL expiry...")
    time.sleep(3)
    
    # 访问过期条目（应重新加载）
    val = cache.get('key_0', lambda: load_data('key_0'))
    print(f"Got (after TTL): {val}")
    
    print(f"\nFinal Stats: {cache.get_stats()}")

