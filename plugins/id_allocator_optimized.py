"""
OpenSynaptic IDAllocator — 优化版本
====================================

改进的 ID 分配器，带有：
- 有界的 _released 集合
- 堆排序快速最小值提取
- 懒清理机制
- 性能监控

替换 plugins/id_allocator.py 中的实现。
"""

import threading
import time
import heapq
from pathlib import Path
from opensynaptic.utils import read_json, write_json, ctx


class IDAllocator:
    """
    高性能的 uint32 ID 分配器，带有自动持久化和资源限制。
    
    改进点:
    - 使用 heapq 替代线性扫描（O(log n) vs O(n)）
    - 有界 _released 集合，防止无限增长
    - 懒清理机制，减少 GC 压力
    - 性能统计和监控
    """
    
    def __init__(self, base_dir: str = None, start_id: int = 1, 
                 end_id: int = 4294967295,
                 persist_file: str = "data/id_allocation.json",
                 max_released_pool: int = 10000):
        """
        初始化 ID 分配器。
        
        Args:
            base_dir: 基础目录（默认使用 ctx.root）
            start_id: ID 范围起点
            end_id: ID 范围终点
            persist_file: 持久化文件相对路径
            max_released_pool: 已释放 ID 集合的最大大小
        """
        self.base_dir = base_dir or ctx.root
        self.start_id = start_id
        self.end_id = end_id
        self.persist_path = str(Path(self.base_dir) / persist_file)
        self.max_released_pool = max_released_pool
        
        # 核心数据结构
        self._allocated = {}          # {id -> {meta, ts}}
        self._released = set()         # 已释放 ID 集合
        self._released_heap = []       # 最小堆（用于快速提取最小 ID）
        self._next_candidate = start_id  # 下一个待分配的 ID
        self._lock = threading.Lock()
        
        # 性能统计
        self.stats = {
            'allocate_calls': 0,
            'release_calls': 0,
            'pool_allocations': 0,
            'cleanups': 0,
            'heap_ops': 0,
        }
        
        self._load()
    
    def _load(self):
        """从磁盘加载已保存的状态。"""
        p = Path(self.persist_path)
        if not p.exists():
            return
        
        try:
            data = read_json(str(p))
            
            # 恢复已分配的 ID
            for k, v in data.get("allocated", {}).items():
                self._allocated[int(k)] = v
            
            # 恢复已释放的 ID
            released_list = data.get("released", [])
            self._released = set(released_list)
            
            # 重建最小堆（仅保留有效的已释放 ID）
            self._released_heap = sorted(self._released)
            heapq.heapify(self._released_heap)
            
            self._next_candidate = data.get("next_candidate", self.start_id)
            
            # 如果加载的 _released 过大，立即触发清理
            if len(self._released) > self.max_released_pool:
                self._cleanup_released()
        
        except Exception as e:
            from opensynaptic.utils import os_log
            os_log.err('IDA', 'LOAD', e, {'path': self.persist_path})
    
    def _save(self):
        """将状态持久化到磁盘。"""
        p = Path(self.persist_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            data = {
                "allocated": {str(k): v for k, v in self._allocated.items()},
                "released": sorted(list(self._released)),  # 排序便于恢复时重建堆
                "next_candidate": self._next_candidate
            }
            write_json(str(p), data, indent=2)
        except Exception as e:
            from opensynaptic.utils import os_log
            os_log.err('IDA', 'SAVE', e, {'path': self.persist_path})
    
    def _cleanup_released(self):
        """
        清理 _released 集合（懒方式）。
        
        保留最小的 50% 已释放 ID（FIFO 风格），丢弃旧的。
        这样在下次分配时优先使用旧的 ID。
        """
        if len(self._released) <= self.max_released_pool:
            return
        
        # 保留最小的 50%
        sorted_released = sorted(self._released)
        keep_count = max(self.max_released_pool // 2, 100)
        self._released = set(sorted_released[:keep_count])
        
        # 重建堆
        self._released_heap = list(self._released)
        heapq.heapify(self._released_heap)
        
        self.stats['cleanups'] += 1
    
    def _allocate_id_nolock(self, meta: dict = None) -> int:
        """
        分配下一个可用 ID（非线程安全，需在锁内调用）。
        
        Args:
            meta: 可选的元数据字典
        
        Returns:
            分配的 ID
        
        Raises:
            RuntimeError: ID 池已用尽
        """
        new_id = None
        
        # 首先尝试从堆中提取最小已释放 ID
        while self._released_heap:
            cand = heapq.heappop(self._released_heap)
            self.stats['heap_ops'] += 1
            
            if cand in self._released:
                self._released.discard(cand)
                new_id = cand
                break
        
        # 如果堆为空或没找到，从 _next_candidate 开始分配新 ID
        if new_id is None:
            # 定期清理已释放集合
            if len(self._released) > self.max_released_pool * 1.5:
                self._cleanup_released()
            
            while self._next_candidate <= self.end_id:
                if self._next_candidate not in self._allocated:
                    new_id = self._next_candidate
                    self._next_candidate += 1
                    break
                self._next_candidate += 1
        
        if new_id is None:
            raise RuntimeError(
                f"[IDAllocator] ID pool exhausted ({self.start_id}-{self.end_id})"
            )
        
        # 记录分配
        self._allocated[new_id] = {
            "meta": meta or {},
            "ts": int(time.time())
        }
        
        return new_id
    
    def allocate_id(self, meta: dict = None) -> int:
        """
        分配单个 ID（线程安全）。
        
        Args:
            meta: 可选的元数据
        
        Returns:
            分配的 ID
        """
        with self._lock:
            self.stats['allocate_calls'] += 1
            new_id = self._allocate_id_nolock(meta=meta)
            self._save()
            return new_id
    
    def allocate_pool(self, count: int, meta: dict = None) -> list:
        """
        一次分配多个 ID（批量，更高效）。
        
        Args:
            count: 要分配的 ID 数量
            meta: 可选的元数据（应用于所有 ID）
        
        Returns:
            分配的 ID 列表
        """
        pool = []
        with self._lock:
            self.stats['pool_allocations'] += 1
            for _ in range(max(0, int(count))):
                try:
                    pool.append(self._allocate_id_nolock(meta=meta))
                except RuntimeError:
                    break
            
            if pool:
                self._save()
        
        return pool
    
    def release_id(self, id_val: int) -> bool:
        """
        释放（归还）一个 ID。
        
        Args:
            id_val: 要释放的 ID
        
        Returns:
            是否成功释放
        """
        with self._lock:
            self.stats['release_calls'] += 1
            
            if id_val in self._allocated:
                del self._allocated[id_val]
                self._released.add(id_val)
                heapq.heappush(self._released_heap, id_val)
                self.stats['heap_ops'] += 1
                
                # 定期检查是否需要清理
                if len(self._released) > self.max_released_pool * 1.2:
                    self._cleanup_released()
                
                self._save()
                return True
            
            return False
    
    def release_pool(self, ids: list) -> int:
        """
        批量释放 ID。
        
        Args:
            ids: ID 列表
        
        Returns:
            实际释放的 ID 数量
        """
        count = 0
        with self._lock:
            for i in ids:
                id_val = int(i)
                if id_val in self._allocated:
                    del self._allocated[id_val]
                    self._released.add(id_val)
                    heapq.heappush(self._released_heap, id_val)
                    self.stats['heap_ops'] += 1
                    count += 1
            
            if count > 0:
                if len(self._released) > self.max_released_pool * 1.2:
                    self._cleanup_released()
                self._save()
        
        return count
    
    def is_allocated(self, id_val: int) -> bool:
        """检查 ID 是否已分配。"""
        return id_val in self._allocated
    
    def get_meta(self, id_val: int) -> dict:
        """获取 ID 的元数据。"""
        return self._allocated.get(id_val, {}).get("meta", {})
    
    def stats_dict(self) -> dict:
        """
        获取分配器统计信息。
        
        Returns:
            统计字典
        """
        with self._lock:
            return {
                "total_allocated": len(self._allocated),
                "total_released": len(self._released),
                "next_candidate": self._next_candidate,
                "range": [self.start_id, self.end_id],
                "released_pool_size": len(self._released),
                "released_heap_size": len(self._released_heap),
                "performance": {
                    "allocate_calls": self.stats['allocate_calls'],
                    "release_calls": self.stats['release_calls'],
                    "pool_allocations": self.stats['pool_allocations'],
                    "cleanups": self.stats['cleanups'],
                    "heap_ops": self.stats['heap_ops'],
                }
            }
    
    # 向后兼容
    def stats(self) -> dict:
        """向后兼容的旧 stats() 方法。"""
        s = self.stats_dict()
        return {
            "total_allocated": s["total_allocated"],
            "total_released": s["total_released"],
            "next_candidate": s["next_candidate"],
            "range": s["range"]
        }


if __name__ == '__main__':
    # 演示
    print("=== IDAllocator Optimization Demo ===\n")
    
    # 创建分配器（使用临时目录）
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        allocator = IDAllocator(base_dir=tmpdir, start_id=1, end_id=1000)
        
        # 批量分配
        print("Allocating 100 IDs...")
        ids = allocator.allocate_pool(100)
        print(f"  Allocated: {ids[:5]} ... (showing first 5)")
        
        # 释放一些
        print("\nReleasing 50 IDs...")
        released = allocator.release_pool(ids[:50])
        print(f"  Released: {released} IDs")
        
        # 重新分配（应该重用已释放的）
        print("\nAllocating 30 more IDs (should reuse released)...")
        new_ids = allocator.allocate_pool(30)
        print(f"  New IDs: {new_ids[:5]} ... (showing first 5)")
        
        # 统计
        print("\nStatistics:")
        stats = allocator.stats_dict()
        for k, v in stats.items():
            if isinstance(v, dict):
                print(f"  {k}:")
                for k2, v2 in v.items():
                    print(f"    {k2}: {v2}")
            else:
                print(f"  {k}: {v}")

