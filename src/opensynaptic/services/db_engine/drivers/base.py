import json
from abc import ABC, abstractmethod
from typing import Any, Iterable, Sequence

class BaseDBDriver(ABC):
    dialect = 'base'

    def __init__(self, config):
        self.config = config or {}
        self.conn = None

    @abstractmethod
    def connect(self):
        raise NotImplementedError

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    @abstractmethod
    def ensure_schema(self):
        raise NotImplementedError

    @abstractmethod
    def insert_packet(self, packet_row):
        raise NotImplementedError

    @abstractmethod
    def insert_sensors(self, sensor_rows):
        raise NotImplementedError

    def _coerce_packet(self, packet_row):
        row = list(packet_row)
        row[4] = json.dumps(row[4], ensure_ascii=False) if isinstance(row[4], dict) else str(row[4])
        return tuple(row)
