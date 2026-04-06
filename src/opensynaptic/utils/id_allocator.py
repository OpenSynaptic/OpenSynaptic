import heapq
import json
import threading
import time
from pathlib import Path

from opensynaptic.utils.logger import os_log
from opensynaptic.utils.paths import ctx, read_json, write_json


class IDAllocator:
    """
    uint32 ID 分配器，带有自动持久化、租约管理和设备去重。

    特性：
    - 设备唯一键去重（device_key / device_id / serial / mac / uuid）
    - 基于租约的 ID 回收（offline_hold_days / adaptive 模式）
    - 自适应租约时长（高注册速率时自动缩短）
    - heapq 优先队列：释放 ID 重用 O(log n)，而非 O(n) min()
    - 可插拔 metrics_sink 回调
    - 线程安全
    """

    def __init__(
        self,
        base_dir: str = None,
        start_id: int = 1,
        end_id: int = 4294967295,
        persist_file: str = "data/id_allocation.json",
        max_released: int = 10000,
        lease_policy: dict = None,
        metrics_sink=None,
    ):
        self.base_dir = base_dir or ctx.root
        self.start_id = start_id
        self.end_id = end_id
        self.persist_path = str(Path(self.base_dir) / persist_file)
        self._lock = threading.Lock()

        self._allocated = {}
        self._released = set()
        self._released_heap = []        # 最小堆，用于 O(log n) 重用最小 ID
        self._device_index = {}
        self._next_candidate = start_id
        self._max_released = max(256, int(max_released or 10000))
        self._metrics_sink = metrics_sink
        self._metrics_last_emit = 0

        self._lease_policy = self._normalize_lease_policy(lease_policy)
        self._metrics_emit_interval = max(
            1, int(self._lease_policy.get('metrics_emit_interval_seconds', 5))
        )
        self._new_device_events = []
        self._ultra_rate_since = 0
        self._metrics = {
            'base_lease_seconds': int(self._lease_policy['base_lease_seconds']),
            'effective_lease_seconds': int(self._lease_policy['base_lease_seconds']),
            'new_device_rate_per_hour': 0.0,
            'ultra_rate_active': False,
            'force_zero_lease_active': False,
            'last_reclaim_count': 0,
            'last_reclaim_at': 0,
            'total_reclaimed': 0,
            'updated_at': int(time.time()),
        }

        self._load()

    # ------------------------------------------------------------------
    # 初始化辅助
    # ------------------------------------------------------------------

    def _normalize_lease_policy(self, policy):
        raw = policy if isinstance(policy, dict) else {}
        base_days = max(0, int(raw.get('offline_hold_days', 30) or 30))
        base_seconds = int(
            raw.get('base_lease_seconds', base_days * 86400) or (base_days * 86400)
        )
        min_seconds = max(0, int(raw.get('min_lease_seconds', 0) or 0))
        return {
            'base_lease_seconds': max(min_seconds, base_seconds),
            'min_lease_seconds': min_seconds,
            'rate_window_seconds': max(
                300, int(raw.get('rate_window_seconds', 3600) or 3600)
            ),
            'high_rate_threshold_per_hour': max(
                1.0, float(raw.get('high_rate_threshold_per_hour', 60.0) or 60.0)
            ),
            'ultra_rate_threshold_per_hour': max(
                1.0, float(raw.get('ultra_rate_threshold_per_hour', 180.0) or 180.0)
            ),
            'ultra_rate_sustain_seconds': max(
                60, int(raw.get('ultra_rate_sustain_seconds', 600) or 600)
            ),
            'high_rate_min_factor': min(
                1.0, max(0.0, float(raw.get('high_rate_min_factor', 0.2) or 0.2))
            ),
            'adaptive_enabled': bool(raw.get('adaptive_enabled', True)),
            'ultra_force_release': bool(raw.get('ultra_force_release', True)),
            'metrics_emit_interval_seconds': max(
                1, int(raw.get('metrics_emit_interval_seconds', 5) or 5)
            ),
        }

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def _load(self):
        p = Path(self.persist_path)
        if not p.exists():
            return
        try:
            data = read_json(str(p))
            now_ts = int(time.time())
            for k, v in data.get("allocated", {}).items():
                aid = int(k)
                rec = dict(v or {})
                rec.setdefault('meta', {})
                rec.setdefault('ts', now_ts)
                rec.setdefault('last_seen', int(rec.get('ts', now_ts)))
                rec.setdefault(
                    'lease_expires_at',
                    int(rec.get('last_seen', now_ts)) + int(self._lease_policy['base_lease_seconds']),
                )
                rec.setdefault('state', 'active')
                rec.setdefault('offline_since', 0)
                key = str(rec.get('device_key', '') or '').strip()
                if key:
                    rec['device_key'] = key
                    self._device_index[key] = aid
                self._allocated[aid] = rec
            self._released = set(data.get("released", []))
            if len(self._released) > self._max_released:
                keep = sorted(self._released)[: self._max_released]
                self._released = set(keep)
            # 重建堆
            self._released_heap = list(self._released)
            heapq.heapify(self._released_heap)
            self._next_candidate = data.get("next_candidate", self.start_id)
            saved_metrics = data.get('lease_metrics', {})
            if isinstance(saved_metrics, dict) and saved_metrics:
                self._metrics.update(saved_metrics)
        except Exception as e:
            os_log.err('IDA', 'LOAD', e, {'path': self.persist_path})

    def _save(self):
        p = Path(self.persist_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "allocated": {str(k): v for k, v in self._allocated.items()},
                "released": sorted(self._released),
                "next_candidate": self._next_candidate,
                "lease_metrics": dict(self._metrics),
            }
            write_json(str(p), data, indent=2)
        except Exception as e:
            os_log.err('IDA', 'SAVE', e, {'path': self.persist_path})

    # ------------------------------------------------------------------
    # 设备键
    # ------------------------------------------------------------------

    def _stable_device_key(self, meta):
        m = meta if isinstance(meta, dict) else {}
        device_meta = m.get('device_meta', {})
        if not isinstance(device_meta, dict):
            device_meta = {}
        explicit = m.get('device_key')
        if explicit:
            return str(explicit).strip()
        for key in ('device_id', 'serial', 'mac', 'uuid'):
            val = m.get(key)
            if val:
                return f'{key}:{val}'
            dval = device_meta.get(key)
            if dval:
                return f'{key}:{dval}'
        if device_meta:
            try:
                return 'meta:' + json.dumps(device_meta, sort_keys=True, ensure_ascii=True)
            except Exception:
                pass
        if m:
            try:
                return 'request:' + json.dumps(m, sort_keys=True, ensure_ascii=True)
            except Exception:
                pass
        return ''

    # ------------------------------------------------------------------
    # 租约 & 速率
    # ------------------------------------------------------------------

    def _default_lease_expires_at(self, now_ts):
        return int(now_ts) + int(self._lease_policy['base_lease_seconds'])

    def _update_rate_metrics_nolock(self, now_ts):
        window = int(self._lease_policy['rate_window_seconds'])
        left = now_ts - window
        self._new_device_events = [ts for ts in self._new_device_events if ts >= left]
        rate = (len(self._new_device_events) * 3600.0 / float(window)) if window > 0 else 0.0
        ultra_threshold = float(self._lease_policy['ultra_rate_threshold_per_hour'])
        if rate >= ultra_threshold:
            if self._ultra_rate_since <= 0:
                self._ultra_rate_since = now_ts
        else:
            self._ultra_rate_since = 0
        self._metrics['new_device_rate_per_hour'] = round(rate, 4)
        self._metrics['ultra_rate_active'] = bool(self._ultra_rate_since > 0)
        return rate

    def _effective_lease_seconds_nolock(self, now_ts):
        base = int(self._lease_policy['base_lease_seconds'])
        if not self._lease_policy.get('adaptive_enabled', True):
            self._metrics['force_zero_lease_active'] = False
            self._metrics['effective_lease_seconds'] = base
            return base
        rate = self._update_rate_metrics_nolock(now_ts)
        high_th = float(self._lease_policy['high_rate_threshold_per_hour'])
        ultra_th = float(self._lease_policy['ultra_rate_threshold_per_hour'])
        sustain = int(self._lease_policy['ultra_rate_sustain_seconds'])
        min_seconds = int(self._lease_policy['min_lease_seconds'])
        if (
            rate >= ultra_th
            and self._ultra_rate_since > 0
            and (now_ts - self._ultra_rate_since) >= sustain
        ):
            self._metrics['force_zero_lease_active'] = True
            self._metrics['effective_lease_seconds'] = 0
            return 0
        self._metrics['force_zero_lease_active'] = False
        if rate <= high_th:
            self._metrics['effective_lease_seconds'] = base
            return base
        factor = high_th / max(rate, 1e-9)
        factor = max(float(self._lease_policy['high_rate_min_factor']), min(1.0, factor))
        eff = max(min_seconds, int(base * factor))
        self._metrics['effective_lease_seconds'] = eff
        return eff

    def _force_offline_zero_lease_nolock(self, now_ts):
        changed = False
        for rec in self._allocated.values():
            if str(rec.get('state', 'active')) != 'offline':
                continue
            if int(rec.get('lease_expires_at', now_ts)) > now_ts:
                rec['lease_expires_at'] = now_ts
                changed = True
        return changed

    def _reclaim_expired_nolock(self, now_ts=None):
        now_ts = int(now_ts or time.time())
        reclaimed = []
        for aid, rec in list(self._allocated.items()):
            expires_at = int(rec.get('lease_expires_at', 0) or 0)
            if expires_at > 0 and now_ts >= expires_at:
                reclaimed.append(aid)
        for aid in reclaimed:
            rec = self._allocated.pop(aid, {})
            key = str(rec.get('device_key', '') or '').strip()
            if key and self._device_index.get(key) == aid:
                self._device_index.pop(key, None)
            self._released.add(aid)
            heapq.heappush(self._released_heap, aid)
        if reclaimed:
            self._trim_released_nolock()
            self._metrics['last_reclaim_count'] = len(reclaimed)
            self._metrics['last_reclaim_at'] = now_ts
            self._metrics['total_reclaimed'] = (
                int(self._metrics.get('total_reclaimed', 0) or 0) + len(reclaimed)
            )
        return reclaimed

    def _trim_released_nolock(self):
        if len(self._released) <= self._max_released:
            return
        keep = sorted(self._released)[: self._max_released]
        self._released = set(keep)
        self._released_heap = list(self._released)
        heapq.heapify(self._released_heap)

    # ------------------------------------------------------------------
    # 指标
    # ------------------------------------------------------------------

    def _emit_metrics_nolock(self, force=False):
        if not callable(self._metrics_sink):
            return
        now_ts = int(time.time())
        if (not force) and (now_ts - self._metrics_last_emit < self._metrics_emit_interval):
            return
        self._metrics['updated_at'] = now_ts
        payload = {
            **self._metrics,
            'allocated_count': len(self._allocated),
            'released_count': len(self._released),
        }
        try:
            self._metrics_sink(payload)
            self._metrics_last_emit = now_ts
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 核心分配逻辑
    # ------------------------------------------------------------------

    def _allocate_id_nolock(self, meta: dict = None) -> int:
        now_ts = int(time.time())
        self._reclaim_expired_nolock(now_ts=now_ts)

        effective_lease_seconds = self._effective_lease_seconds_nolock(now_ts)
        if effective_lease_seconds <= 0 and self._lease_policy.get('ultra_force_release', True):
            if self._force_offline_zero_lease_nolock(now_ts):
                self._reclaim_expired_nolock(now_ts=now_ts)

        # 设备去重：同一设备复用其已有 ID
        stable_key = self._stable_device_key(meta)
        if stable_key:
            existing = self._device_index.get(stable_key)
            if existing in self._allocated:
                rec = self._allocated[existing]
                rec['last_seen'] = now_ts
                rec['lease_expires_at'] = self._default_lease_expires_at(now_ts)
                rec['meta'] = meta or rec.get('meta', {})
                rec['state'] = 'active'
                rec['offline_since'] = 0
                return existing

        new_id = None

        # 优先从堆中取最小已释放 ID（O(log n)）
        while self._released_heap:
            cand = heapq.heappop(self._released_heap)
            if cand in self._released:
                self._released.discard(cand)
                new_id = cand
                break
            # 堆中的 cand 已被其他路径消费，跳过

        # 无可复用 ID，分配新 ID
        if new_id is None:
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

        self._allocated[new_id] = {
            "meta": meta or {},
            "ts": now_ts,
            "last_seen": now_ts,
            "lease_expires_at": self._default_lease_expires_at(now_ts),
            "device_key": stable_key,
            "state": "active",
            "offline_since": 0,
        }
        if stable_key:
            self._device_index[stable_key] = new_id
        self._new_device_events.append(now_ts)
        self._update_rate_metrics_nolock(now_ts)
        return new_id

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def allocate_id(self, meta: dict = None) -> int:
        with self._lock:
            new_id = self._allocate_id_nolock(meta=meta)
            self._save()
            self._emit_metrics_nolock()
            return new_id

    def allocate_pool(self, count: int, meta: dict = None) -> list:
        pool = []
        with self._lock:
            for _ in range(max(0, int(count))):
                try:
                    pool.append(self._allocate_id_nolock(meta=meta))
                except RuntimeError:
                    break
            if pool:
                self._save()
                self._emit_metrics_nolock()
        return pool

    def release_id(self, id_val: int, immediate: bool = False) -> bool:
        with self._lock:
            if id_val in self._allocated:
                rec = self._allocated.get(id_val, {})
                now_ts = int(time.time())
                if immediate:
                    rec['lease_expires_at'] = now_ts
                else:
                    lease_seconds = self._effective_lease_seconds_nolock(now_ts)
                    rec['lease_expires_at'] = (
                        now_ts + lease_seconds if lease_seconds > 0 else now_ts
                    )
                rec['state'] = 'offline'
                rec['offline_since'] = now_ts
                self._reclaim_expired_nolock(now_ts=now_ts)
                self._save()
                self._emit_metrics_nolock()
                return True
            return False

    def release_pool(self, ids: list, immediate: bool = False) -> int:
        count = 0
        for i in ids:
            if self.release_id(int(i), immediate=immediate):
                count += 1
        return count

    def touch(self, aid: int, meta: dict = None) -> bool:
        with self._lock:
            rec = self._allocated.get(int(aid))
            if not rec:
                return False
            now_ts = int(time.time())
            rec['last_seen'] = now_ts
            rec['lease_expires_at'] = self._default_lease_expires_at(now_ts)
            rec['state'] = 'active'
            rec['offline_since'] = 0
            if isinstance(meta, dict) and meta:
                rec['meta'] = meta
                key = self._stable_device_key(meta)
                if key:
                    old = str(rec.get('device_key', '') or '').strip()
                    if old and self._device_index.get(old) == int(aid):
                        self._device_index.pop(old, None)
                    rec['device_key'] = key
                    self._device_index[key] = int(aid)
            self._save()
            self._emit_metrics_nolock()
            return True

    def reclaim_expired(self) -> int:
        with self._lock:
            count = len(self._reclaim_expired_nolock())
            if count:
                self._save()
                self._emit_metrics_nolock(force=True)
            return count

    def is_allocated(self, id_val: int) -> bool:
        return id_val in self._allocated

    def get_meta(self, id_val: int) -> dict:
        return self._allocated.get(id_val, {}).get("meta", {})

    def stats(self) -> dict:
        with self._lock:
            self._update_rate_metrics_nolock(int(time.time()))
        return {
            "total_allocated": len(self._allocated),
            "total_released": len(self._released),
            "next_candidate": self._next_candidate,
            "range": [self.start_id, self.end_id],
            "lease_policy": dict(self._lease_policy),
            "lease_metrics": dict(self._metrics),
        }
