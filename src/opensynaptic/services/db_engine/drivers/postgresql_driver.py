from typing import Any, Iterable, Sequence
import os
from .base import BaseDBDriver
POSTGRES_CREATE_PACKETS = '\nCREATE TABLE IF NOT EXISTS os_packets (\n    packet_uuid VARCHAR(64) PRIMARY KEY,\n    device_id VARCHAR(255) NOT NULL,\n    device_status VARCHAR(32) NOT NULL,\n    timestamp_raw BIGINT NOT NULL,\n    payload_json JSONB NOT NULL,\n    created_at BIGINT NOT NULL\n)\n'
POSTGRES_CREATE_SENSORS = '\nCREATE TABLE IF NOT EXISTS os_sensors (\n    packet_uuid VARCHAR(64) NOT NULL,\n    sensor_index INTEGER NOT NULL,\n    sensor_id VARCHAR(255) NOT NULL,\n    sensor_status VARCHAR(32) NOT NULL,\n    normalized_value DOUBLE PRECISION NULL,\n    normalized_unit VARCHAR(64) NULL\n)\n'
POSTGRES_INSERT_PACKET = '\nINSERT INTO os_packets (\n    packet_uuid, device_id, device_status, timestamp_raw, payload_json, created_at\n) VALUES (%s, %s, %s, %s, %s, %s)\n'
POSTGRES_INSERT_SENSOR = '\nINSERT INTO os_sensors (\n    packet_uuid, sensor_index, sensor_id, sensor_status, normalized_value, normalized_unit\n) VALUES (%s, %s, %s, %s, %s, %s)\n'

class PostgresDriver(BaseDBDriver):
    dialect = 'postgresql'

    def connect(self):
        if self.conn is not None:
            return self.conn
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError('psycopg is required for PostgreSQL driver') from exc
        params = {'host': self.config.get('host', '127.0.0.1'), 'port': int(self.config.get('port', 5432)), 'user': self.config.get('user'), 'password': os.getenv('OS_DB_PASSWORD') or self.config.get('password'), 'dbname': self.config.get('database')}
        self.conn = psycopg.connect(**params)
        self.conn.autocommit = False
        return self.conn

    def ensure_schema(self):
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(POSTGRES_CREATE_PACKETS)
            cur.execute(POSTGRES_CREATE_SENSORS)
        conn.commit()

    def insert_packet(self, packet_row):
        conn = self.connect()
        with conn.cursor() as cur:
            cur.execute(POSTGRES_INSERT_PACKET, self._coerce_packet(packet_row))

    def insert_sensors(self, sensor_rows):
        rows = list(sensor_rows)
        if not rows:
            return
        conn = self.connect()
        with conn.cursor() as cur:
            cur.executemany(POSTGRES_INSERT_SENSOR, rows)
