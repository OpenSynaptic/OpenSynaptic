from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg

def send(payload, config):
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    port = opts.get('port', 'UART0')
    baudrate = int(opts.get('baudrate', 115200))
    if isinstance(payload, str):
        payload = payload.encode('utf-8')
    frame_start = b'\x02'
    frame_end = b'\x03'
    packet = frame_start + payload + frame_end
    duration = len(packet) * 10 / max(baudrate, 1)
    os_log.log_with_const('info', LogMsg.UART_SEND, port=port, total_len=len(packet))
    os_log.log_with_const('info', LogMsg.UART_DURATION, duration=duration)
    return True
