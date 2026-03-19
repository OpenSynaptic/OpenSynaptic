from typing import Any, Iterable, Sequence
from .base import BaseDBDriver
MYSQL_CREATE_PACKETS = '\nCREATE TABLE IF NOT EXISTS os_packets (\n    packet_uuid VARCHAR(64) PRIMARY KEY,\n    device_id VARCHAR(255) NOT NULL,\n    device_status VARCHAR(32) NOT NULL,\n    timestamp_raw BIGINT NOT NULL,\n    payload_json JSON NOT NULL,\n    created_at BIGINT NOT NULL\n)\n'
MYSQL_CREATE_SENSORS = '\nCREATE TABLE IF NOT EXISTS os_sensors (\n    packet_uuid VARCHAR(64) NOT NULL,\n    sensor_index INT NOT NULL,\n    sensor_id VARCHAR(255) NOT NULL,\n    sensor_status VARCHAR(32) NOT NULL,\n    normalized_value DOUBLE NULL,\n    normalized_unit VARCHAR(64) NULL,\n    INDEX idx_os_sensors_packet_uuid (packet_uuid)\n)\n'
MYSQL_INSERT_PACKET = '\nINSERT INTO os_packets (\n    packet_uuid, device_id, device_status, timestamp_raw, payload_json, created_at\n) VALUES (%s, %s, %s, %s, %s, %s)\n'
MYSQL_INSERT_SENSOR = '\nINSERT INTO os_sensors (\n    packet_uuid, sensor_index, sensor_id, sensor_status, normalized_value, normalized_unit\n) VALUES (%s, %s, %s, %s, %s, %s)\n'

class MySQLDriver(BaseDBDriver):
    dialect = 'mysql'

    def connect(self):
        if self.conn is not None:
            return self.conn
        try:
            import mysql.connector
        except ImportError as exc:
            raise RuntimeError('mysql-connector-python is required for MySQL driver') from exc
        params = {'host': self.config.get('host', '127.0.0.1'), 'port': int(self.config.get('port', 3306)), 'user': self.config.get('user'), 'password': self.config.get('password'), 'database': self.config.get('database'), 'autocommit': False}
        self.conn = mysql.connector.connect(**params)
        return self.conn

    def ensure_schema(self):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(MYSQL_CREATE_PACKETS)
        cur.execute(MYSQL_CREATE_SENSORS)
        cur.close()
        conn.commit()

    def insert_packet(self, packet_row):
        conn = self.connect()
        cur = conn.cursor()
        cur.execute(MYSQL_INSERT_PACKET, self._coerce_packet(packet_row))
        cur.close()

    def insert_sensors(self, sensor_rows):
        rows = list(sensor_rows)
        if not rows:
            return
        conn = self.connect()
        cur = conn.cursor()
        cur.executemany(MYSQL_INSERT_SENSOR, rows)
        cur.close()
