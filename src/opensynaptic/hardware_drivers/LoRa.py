try:
    import serial
    import serial.tools.list_ports
except Exception:
    serial = None
import time
from opensynaptic.utils import (
    os_log,
    LogMsg,
)

class LoRaDriver:

    def __init__(self, baudrate=9600, timeout=2):
        self.baudrate = baudrate
        self.timeout = timeout
        self.ser = self._auto_detect_port()

    def _auto_detect_port(self):
        if serial is None:
            os_log.err('LOR', 'IO', Exception('pyserial not installed'), {})
            return None
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            os_log.err('LOR', 'IO', Exception('No serial ports detected'), {})
            return None
        target_port = None
        for p in ports:
            desc = p.description.upper()
            if 'USB' in desc or 'UART' in desc or 'CH340' in desc or ('CP210' in desc):
                target_port = p.device
                break
        if not target_port:
            target_port = ports[0].device
        try:
            ser = serial.Serial(target_port, self.baudrate, timeout=self.timeout)
            os_log.log_with_const('info', LogMsg.LORA_CONNECTED, port=target_port)
            return ser
        except Exception as e:
            os_log.err('LOR', 'IO', e, {'port': target_port})
            return None

    def send(self, payload):
        if not self.ser or not getattr(self.ser, 'is_open', False):
            os_log.log_with_const('error', LogMsg.LORA_NOT_READY)
            return None
        if isinstance(payload, str):
            try:
                data = bytes.fromhex(payload)
            except ValueError:
                data = payload.encode('utf-8')
        else:
            data = payload
        try:
            if hasattr(self.ser, 'reset_input_buffer'):
                self.ser.reset_input_buffer()
            os_log.log_with_const('info', LogMsg.LORA_SENDING, len=len(data), hex=data.hex().upper())
            if hasattr(self.ser, 'write'):
                self.ser.write(data)
                if hasattr(self.ser, 'flush'):
                    self.ser.flush()
            time.sleep(0.5)
            if hasattr(self.ser, 'in_waiting') and self.ser.in_waiting > 0:
                response = self.ser.read(self.ser.in_waiting)
                os_log.log_with_const('info', LogMsg.LORA_RESPONSE, hex=response.hex().upper())
                return response
            return b'OK'
        except Exception as e:
            os_log.err('LOR', 'IO', e, {'len': len(data) if 'data' in locals() else None})
            return None

    def receive(self):
        if not self.ser or not getattr(self.ser, 'is_open', False):
            return None
        try:
            waiting = getattr(self.ser, 'in_waiting', 0)
            if waiting <= 0:
                return None
            return self.ser.read(waiting)
        except Exception as e:
            os_log.err('LOR', 'RECV', e, {})
            return None

    def close(self):
        if self.ser and getattr(self.ser, 'is_open', False):
            try:
                self.ser.close()
            except Exception:
                pass
            os_log.log_with_const('info', LogMsg.LORA_CLOSED)
_driver_instance = None

def send(payload):
    global _driver_instance
    if _driver_instance is None:
        _driver_instance = LoRaDriver()
    return _driver_instance.send(payload)
if __name__ == '__main__':
    test_packet = 'AA01DEAFBEEF'
    send(test_packet)
