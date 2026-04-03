import math
from opensynaptic.utils import (
    os_log,
    LogMsg,
)

class CAN_Driver:

    def __init__(self, can_id=291):
        self.can_id = can_id
        self.MTU = 8
        self._loopback_frames = []

    def segment_send(self, payload):
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
            self._loopback_frames.append(bytes(chunk))
        return frames

    def receive(self):
        """Return one frame payload in local loopback mode.

        This keeps protocol listener contract intact when a real CAN backend
        is not wired in the current runtime.
        """
        if not self._loopback_frames:
            return None
        return self._loopback_frames.pop(0)
