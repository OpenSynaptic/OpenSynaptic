from opensynaptic.utils import (
    os_log,
    LogMsg,
    as_readonly_view,
)

def send(payload, config):
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    port = opts.get('port', 'UART0')
    baudrate = int(opts.get('baudrate', 115200))
    view = as_readonly_view(payload)
    packet = bytearray(2 + len(view))
    packet[0] = 2
    packet[-1] = 3
    packet[1:-1] = view
    duration = len(packet) * 10 / max(baudrate, 1)
    os_log.log_with_const('info', LogMsg.UART_SEND, port=port, total_len=len(packet))
    os_log.log_with_const('info', LogMsg.UART_DURATION, duration=duration)
    return True
