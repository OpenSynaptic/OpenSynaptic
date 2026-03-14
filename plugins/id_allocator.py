import threading
import time
from pathlib import Path
from opensynaptic.utils.paths import read_json, write_json, ctx


class IDAllocator:
    def __init__(self, base_dir: str = None, start_id: int = 1, end_id: int = 4294967295,
                 persist_file: str = "data/id_allocation.json"):
        self.base_dir = base_dir or ctx.root
        self.start_id = start_id
        self.end_id = end_id
        self.persist_path = str(Path(self.base_dir) / persist_file)
        self._lock = threading.Lock()

        self._allocated = {}
        self._released = set()
        self._next_candidate = start_id

        self._load()

    def _load(self):
        p = Path(self.persist_path)
        if not p.exists():
            return
        data = read_json(str(p))
        for k, v in data.get("allocated", {}).items():
            self._allocated[int(k)] = v
        self._released = set(data.get("released", []))
        self._next_candidate = data.get("next_candidate", self.start_id)

    def _save(self):
        p = Path(self.persist_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "allocated": {str(k): v for k, v in self._allocated.items()},
            "released": list(self._released),
            "next_candidate": self._next_candidate
        }
        write_json(str(p), data, indent=2)

    def _allocate_id_nolock(self, meta: dict = None) -> int:
        new_id = None

        if self._released:
            new_id = min(self._released)
            self._released.discard(new_id)

        if new_id is None:
            while self._next_candidate <= self.end_id:
                if self._next_candidate not in self._allocated:
                    new_id = self._next_candidate
                    self._next_candidate += 1
                    break
                self._next_candidate += 1

        if new_id is None:
            raise RuntimeError(f"[IDAllocator] ID 池耗盡 ({self.start_id}-{self.end_id})")

        self._allocated[new_id] = {
            "meta": meta or {},
            "ts": int(time.time())
        }
        return new_id

    def allocate_id(self, meta: dict = None) -> int:
        with self._lock:
            new_id = self._allocate_id_nolock(meta=meta)
            self._save()
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
        return pool

    def release_id(self, id_val: int) -> bool:
        with self._lock:
            if id_val in self._allocated:
                del self._allocated[id_val]
                self._released.add(id_val)
                self._save()
                return True
            return False

    def release_pool(self, ids: list) -> int:
        count = 0
        for i in ids:
            if self.release_id(int(i)):
                count += 1
        return count

    def is_allocated(self, id_val: int) -> bool:
        return id_val in self._allocated

    def get_meta(self, id_val: int) -> dict:
        return self._allocated.get(id_val, {}).get("meta", {})

    def stats(self) -> dict:
        return {
            "total_allocated": len(self._allocated),
            "total_released": len(self._released),
            "next_candidate": self._next_candidate,
            "range": [self.start_id, self.end_id]
        }