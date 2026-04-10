import sqlite3
from typing import Any, Iterable, Sequence
from .base import BaseDBDriver
SQLITE_CREATE_PACKETS = '\nCREATE TABLE IF NOT EXISTS os_packets (\n    packet_uuid TEXT PRIMARY KEY,\n    device_id TEXT NOT NULL,\n    device_status TEXT NOT NULL,\n    timestamp_raw INTEGER NOT NULL,\n    payload_json TEXT NOT NULL,\n    created_at INTEGER NOT NULL\n)\n'
SQLITE_CREATE_SENSORS = '\nCREATE TABLE IF NOT EXISTS os_sensors (\n    packet_uuid TEXT NOT NULL,\n    sensor_index INTEGER NOT NULL,\n    sensor_id TEXT NOT NULL,\n    sensor_status TEXT NOT NULL,\n    normalized_value REAL,\n    normalized_unit TEXT,\n    FOREIGN KEY(packet_uuid) REFERENCES os_packets(packet_uuid)\n)\n'
SQLITE_INSERT_PACKET = '\nINSERT INTO os_packets (\n    packet_uuid, device_id, device_status, timestamp_raw, payload_json, created_at\n) VALUES (?, ?, ?, ?, ?, ?)\n'
SQLITE_INSERT_SENSOR = '\nINSERT INTO os_sensors (\n    packet_uuid, sensor_index, sensor_id, sensor_status, normalized_value, normalized_unit\n) VALUES (?, ?, ?, ?, ?, ?)\n'

class SQLiteDriver(BaseDBDriver):
    dialect = 'sqlite'

    def connect(self):
        if self.conn is None:
            db_path = self.config.get('path') or self.config.get('database') or ':memory:'
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
        return self.conn

    def ensure_schema(self):
        conn = self.connect()
        conn.execute(SQLITE_CREATE_PACKETS)
        conn.execute(SQLITE_CREATE_SENSORS)
        conn.commit()

    def insert_packet(self, packet_row):
        conn = self.connect()
        conn.execute(SQLITE_INSERT_PACKET, self._coerce_packet(packet_row))

    def insert_sensors(self, sensor_rows):
        rows = list(sensor_rows)
        if not rows:
            return
        conn = self.connect()
        conn.executemany(SQLITE_INSERT_SENSOR, rows)
