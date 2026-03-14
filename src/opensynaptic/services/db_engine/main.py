import threading
import time
import uuid
from typing import Any
from opensynaptic.services.db_engine.drivers import create_driver
from opensynaptic.utils.logger import os_log

class DatabaseManager:
    """Thread-safe SQL export manager for normalized OpenSynaptic facts."""

    def __init__(self, dialect, config=None):
        self.dialect = str(dialect or '').strip().lower()
        self.config = config or {}
        self.driver = create_driver(self.dialect, self.config)
        self._lock = threading.RLock()
        self._ready = False

    @classmethod
    def from_opensynaptic_config(cls, config):
        storage = (config or {}).get('storage', {})
        sql_cfg = storage.get('sql', {})
        if not sql_cfg.get('enabled', False):
            return None
        dialect = sql_cfg.get('dialect', 'sqlite')
        driver_cfg = sql_cfg.get('driver', {})
        return cls(dialect=dialect, config=driver_cfg)

    def connect(self):
        with self._lock:
            self.driver.connect()
            if not self._ready:
                self.driver.ensure_schema()
                self._ready = True

    def auto_load(self):
        self.connect()
        return self

    def close(self):
        with self._lock:
            self.driver.close()
            self._ready = False

    def export_fact(self, fact):
        if not isinstance(fact, dict) or not fact:
            return False
        packet_uuid = str(uuid.uuid4())
        packet_row, sensor_rows = self._build_rows(packet_uuid, fact)
        with self._lock:
            try:
                self.connect()
                self.driver.insert_packet(packet_row)
                self.driver.insert_sensors(sensor_rows)
                self.driver.conn.commit()
                return True
            except Exception as exc:
                try:
                    if self.driver.conn is not None:
                        self.driver.conn.rollback()
                except Exception:
                    pass
                os_log.err('DB', 'EXPORT', exc, {'dialect': self.dialect})
                return False

    def export_many(self, facts):
        if not facts:
            return 0
        ok_count = 0
        with self._lock:
            try:
                self.connect()
                for fact in facts:
                    if not isinstance(fact, dict) or not fact:
                        continue
                    packet_uuid = str(uuid.uuid4())
                    packet_row, sensor_rows = self._build_rows(packet_uuid, fact)
                    self.driver.insert_packet(packet_row)
                    self.driver.insert_sensors(sensor_rows)
                    ok_count += 1
                self.driver.conn.commit()
            except Exception as exc:
                try:
                    if self.driver.conn is not None:
                        self.driver.conn.rollback()
                except Exception:
                    pass
                os_log.err('DB', 'BATCH_EXPORT', exc, {'dialect': self.dialect})
                return ok_count
        return ok_count

    def _build_rows(self, packet_uuid, fact):
        now = int(time.time())
        timestamp_raw = self._safe_int(fact.get('t', now), default=now)
        packet_row = (packet_uuid, str(fact.get('id', 'UNKNOWN')), str(fact.get('s', 'UNKNOWN')), timestamp_raw, fact, now)
        sensor_rows = []
        idx = 1
        while True:
            key_base = 's' + str(idx)
            has_any = key_base + '_id' in fact or key_base + '_v' in fact or key_base + '_u' in fact or (key_base + '_s' in fact)
            if not has_any:
                break
            sensor_rows.append((packet_uuid, idx, str(fact.get(key_base + '_id', '')), str(fact.get(key_base + '_s', 'UNKNOWN')), self._safe_float(fact.get(key_base + '_v')), str(fact.get(key_base + '_u', '')) if fact.get(key_base + '_u') is not None else None))
            idx += 1
        return (packet_row, sensor_rows)

    @staticmethod
    def _safe_int(value, default=0):
        try:
            return int(value)
        except Exception:
            return int(default)

    @staticmethod
    def _safe_float(value):
        if value is None:
            return None
        try:
            return float(value)
        except Exception:
            return None
