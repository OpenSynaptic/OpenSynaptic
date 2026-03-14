import math
from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg

class CAN_Driver:
    """ 模拟 CAN 总线：强制 8 字节分片 (CAN Standard Frame) """

    def __init__(self, can_id=291):
        self.can_id = can_id
        self.MTU = 8

    def segment_send(self, payload):
        """ 将 1200 Byte 塌缩数据拆分为 150 个 CAN 帧 """
        if isinstance(payload, str):
            payload = payload.encode('utf-8')
        total_len = len(payload)
        chunks = math.ceil(total_len / self.MTU)
        os_log.log_with_const('info', LogMsg.CAN_SEND, can_id=hex(self.can_id), chunks=chunks)
        frames = []
        for i in range(chunks):
            start = i * self.MTU
            end = start + self.MTU
            chunk = payload[start:end]
            frames.append({'id': self.can_id, 'dlc': len(chunk), 'data': chunk})
        return frames
