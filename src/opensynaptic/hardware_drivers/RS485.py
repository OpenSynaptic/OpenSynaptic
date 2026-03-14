try:
    import serial
except Exception:
    serial = None
from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg

class RS485_Driver:
    """ 模拟 RS485/UART：流式传输，带简单的帧校验 """

    def __init__(self, port='COM1', baudrate=9600):
        self.port = port
        self.baud = baudrate
        self.STX = b'\x02'
        self.ETX = b'\x03'

    def send(self, payload):
        """ 模拟 RS485 发送：[STX] + [DATA] + [LRC校验] + [ETX] """
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
                pass
            except Exception as e:
                os_log.err('RS485', 'IO', e, {'port': self.port})
        return packet

    def receive_sync(self, raw_stream):
        """ 模拟从原始字节流中提取 OS 塌缩数据 """
        if self.STX in raw_stream and self.ETX in raw_stream:
            content = raw_stream.split(self.STX)[1].split(self.ETX)[0]
            data = content[:-1]
            return data.decode('utf-8', errors='ignore')
        return None
