try:
    import serial
except Exception:
    serial = None
from opensynaptic.utils import (
    os_log,
    LogMsg,
)

class RS485_Driver:

    def __init__(self, port='COM1', baudrate=9600, timeout=0.2):
        self.port = port
        self.baud = baudrate
        self.timeout = timeout
        self.STX = b'\x02'
        self.ETX = b'\x03'
        self.ser = None
        if serial is not None:
            try:
                self.ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
            except Exception as e:
                os_log.err('RS485', 'OPEN', e, {'port': self.port, 'baud': self.baud})

    def send(self, payload):
        if isinstance(payload, str):
            payload = payload.encode('utf-8')
        lrc = 0
        for byte in payload:
            lrc = lrc + byte & 255
        lrc_byte = bytes([lrc])
        packet = self.STX + payload + lrc_byte + self.ETX
        os_log.log_with_const('info', LogMsg.RS485_SEND, port=self.port, len=len(packet))
        if serial is None:
            os_log.err('RS485', 'IO', Exception('pyserial not installed'), {})
        else:
            try:
                if self.ser and getattr(self.ser, 'is_open', False):
                    self.ser.write(packet)
                    if hasattr(self.ser, 'flush'):
                        self.ser.flush()
            except Exception as e:
                os_log.err('RS485', 'IO', e, {'port': self.port})
        return packet

    def receive_sync(self, raw_stream, as_bytes=True):
        if self.STX in raw_stream and self.ETX in raw_stream:
            content = raw_stream.split(self.STX)[1].split(self.ETX)[0]
            data = content[:-1]
            if as_bytes:
                return data
            return data.decode('utf-8', errors='ignore')
        return None

    def receive(self):
        if not self.ser or not getattr(self.ser, 'is_open', False):
            return None
        try:
            waiting = getattr(self.ser, 'in_waiting', 0)
            if waiting <= 0:
                return None
            raw = self.ser.read(waiting)
            if not raw:
                return None
            return self.receive_sync(raw, as_bytes=True)
        except Exception as e:
            os_log.err('RS485', 'RECV', e, {'port': self.port})
            return None

    def close(self):
        if self.ser and getattr(self.ser, 'is_open', False):
            try:
                self.ser.close()
            except Exception:
                pass
