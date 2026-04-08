import json
import threading
import time
import uuid
from typing import Any
from opensynaptic.services.db_engine.drivers import create_driver
from opensynaptic.utils import os_log

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

    # ------------------------------------------------------------------
    # Data query API (read-only)
    # ------------------------------------------------------------------

    def _ph(self):
        """Return SQL placeholder for this dialect."""
        return '?' if self.dialect == 'sqlite' else '%s'

    def query_packets(self, device_id=None, since=None, until=None, status=None, limit=50, offset=0):
        """Return paginated packets from os_packets ordered by timestamp descending."""
        limit = max(1, min(500, self._safe_int(limit, 50)))
        offset = max(0, self._safe_int(offset, 0))
        ph = self._ph()
        where, params = [], []
        if device_id:
            where.append(f'device_id = {ph}')
            params.append(str(device_id))
        if since is not None:
            where.append(f'timestamp_raw >= {ph}')
            params.append(self._safe_int(since, 0))
        if until is not None:
            where.append(f'timestamp_raw <= {ph}')
            params.append(self._safe_int(until, 0))
        if status:
            where.append(f'device_status = {ph}')
            params.append(str(status))
        where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
        count_sql = f'SELECT COUNT(*) FROM os_packets {where_sql}'
        data_sql = (
            f'SELECT packet_uuid, device_id, device_status, timestamp_raw, payload_json, created_at '
            f'FROM os_packets {where_sql} ORDER BY timestamp_raw DESC LIMIT {limit} OFFSET {offset}'
        )
        with self._lock:
            try:
                self.connect()
                total = self.driver.conn.execute(count_sql, params).fetchone()[0]
                rows = self.driver.conn.execute(data_sql, params).fetchall()
                packets = []
                for r in rows:
                    try:
                        payload = json.loads(r[4]) if isinstance(r[4], str) else r[4]
                    except Exception:
                        payload = r[4]
                    packets.append({
                        'packet_uuid': r[0],
                        'device_id': r[1],
                        'device_status': r[2],
                        'timestamp_raw': r[3],
                        'payload_json': payload,
                        'created_at': r[5],
                    })
                return {'packets': packets, 'total': total, 'limit': limit, 'offset': offset}
            except Exception as exc:
                os_log.err('DB', 'QUERY_PACKETS', exc, {'dialect': self.dialect})
                return {'packets': [], 'total': 0, 'limit': limit, 'offset': offset, 'error': str(exc)}

    def query_packet(self, packet_uuid):
        """Return a single packet row plus its sensor rows, or None if not found."""
        ph = self._ph()
        with self._lock:
            try:
                self.connect()
                row = self.driver.conn.execute(
                    f'SELECT packet_uuid, device_id, device_status, timestamp_raw, payload_json, created_at '
                    f'FROM os_packets WHERE packet_uuid = {ph}',
                    (str(packet_uuid),),
                ).fetchone()
                if row is None:
                    return None
                try:
                    payload = json.loads(row[4]) if isinstance(row[4], str) else row[4]
                except Exception:
                    payload = row[4]
                packet = {
                    'packet_uuid': row[0],
                    'device_id': row[1],
                    'device_status': row[2],
                    'timestamp_raw': row[3],
                    'payload_json': payload,
                    'created_at': row[5],
                }
                sensor_rows = self.driver.conn.execute(
                    f'SELECT sensor_index, sensor_id, sensor_status, normalized_value, normalized_unit '
                    f'FROM os_sensors WHERE packet_uuid = {ph} ORDER BY sensor_index',
                    (str(packet_uuid),),
                ).fetchall()
                sensors = [
                    {
                        'sensor_index': s[0],
                        'sensor_id': s[1],
                        'sensor_status': s[2],
                        'normalized_value': s[3],
                        'normalized_unit': s[4],
                    }
                    for s in sensor_rows
                ]
                return {'packet': packet, 'sensors': sensors}
            except Exception as exc:
                os_log.err('DB', 'QUERY_PACKET', exc, {'dialect': self.dialect})
                return None

    def query_sensors(self, device_id=None, sensor_id=None, since=None, until=None, limit=50, offset=0):
        """Return paginated sensor rows joined with packet metadata."""
        limit = max(1, min(500, self._safe_int(limit, 50)))
        offset = max(0, self._safe_int(offset, 0))
        ph = self._ph()
        where, params = [], []
        if device_id:
            where.append(f'p.device_id = {ph}')
            params.append(str(device_id))
        if sensor_id:
            where.append(f's.sensor_id = {ph}')
            params.append(str(sensor_id))
        if since is not None:
            where.append(f'p.timestamp_raw >= {ph}')
            params.append(self._safe_int(since, 0))
        if until is not None:
            where.append(f'p.timestamp_raw <= {ph}')
            params.append(self._safe_int(until, 0))
        where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''
        count_sql = (
            f'SELECT COUNT(*) FROM os_sensors s '
            f'JOIN os_packets p ON s.packet_uuid = p.packet_uuid {where_sql}'
        )
        data_sql = (
            f'SELECT s.packet_uuid, s.sensor_index, s.sensor_id, s.sensor_status, '
            f's.normalized_value, s.normalized_unit, p.device_id, p.timestamp_raw '
            f'FROM os_sensors s JOIN os_packets p ON s.packet_uuid = p.packet_uuid '
            f'{where_sql} ORDER BY p.timestamp_raw DESC, s.sensor_index '
            f'LIMIT {limit} OFFSET {offset}'
        )
        with self._lock:
            try:
                self.connect()
                total = self.driver.conn.execute(count_sql, params).fetchone()[0]
                rows = self.driver.conn.execute(data_sql, params).fetchall()
                sensors = [
                    {
                        'packet_uuid': r[0],
                        'sensor_index': r[1],
                        'sensor_id': r[2],
                        'sensor_status': r[3],
                        'normalized_value': r[4],
                        'normalized_unit': r[5],
                        'device_id': r[6],
                        'timestamp_raw': r[7],
                    }
                    for r in rows
                ]
                return {'sensors': sensors, 'total': total, 'limit': limit, 'offset': offset}
            except Exception as exc:
                os_log.err('DB', 'QUERY_SENSORS', exc, {'dialect': self.dialect})
                return {'sensors': [], 'total': 0, 'limit': limit, 'offset': offset, 'error': str(exc)}

    def query_devices(self, limit=100, offset=0):
        """Return distinct devices with last_seen timestamp and packet count."""
        limit = max(1, min(500, self._safe_int(limit, 100)))
        offset = max(0, self._safe_int(offset, 0))
        with self._lock:
            try:
                self.connect()
                total = self.driver.conn.execute('SELECT COUNT(DISTINCT device_id) FROM os_packets').fetchone()[0]
                rows = self.driver.conn.execute(
                    f'SELECT device_id, MAX(timestamp_raw) as last_seen, COUNT(*) as packet_count '
                    f'FROM os_packets GROUP BY device_id ORDER BY last_seen DESC '
                    f'LIMIT {limit} OFFSET {offset}'
                ).fetchall()
                devices = [
                    {'device_id': r[0], 'last_seen': r[1], 'packet_count': r[2]}
                    for r in rows
                ]
                return {'devices': devices, 'total': total, 'limit': limit, 'offset': offset}
            except Exception as exc:
                os_log.err('DB', 'QUERY_DEVICES', exc, {'dialect': self.dialect})
                return {'devices': [], 'total': 0, 'limit': limit, 'offset': offset, 'error': str(exc)}
