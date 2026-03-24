from opensynaptic.utils import (
    os_log,
    LogMsg,
    to_wire_payload,
)

def send(payload, config):
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    port = opts.get('port', 'UART0')
    baudrate = int(opts.get('baudrate', 115200))
    view = to_wire_payload(payload, config, force_zero_copy=True)
    packet = bytearray(2 + len(view))
    packet[0] = 2
    packet[-1] = 3
    packet[1:-1] = view
    duration = len(packet) * 10 / max(baudrate, 1)
    os_log.log_with_const('info', LogMsg.UART_SEND, port=port, total_len=len(packet))
    os_log.log_with_const('info', LogMsg.UART_DURATION, duration=duration)
    return True


def listen(config, callback):
    """
    Listen for incoming UART packets with STX(0x02)/ETX(0x03) framing.
    
    Args:
        config: dict with port/baudrate in physical_options
        callback: callable(data, addr) to handle received packets
    
    Returns:
        None (blocking listener)
    """
    try:
        import serial
    except ImportError:
        os_log.err('PHY', 'UART_LISTEN', 'pyserial not installed', {'port': 'unknown'})
        return
    
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    port = opts.get('port', 'UART0')
    baudrate = int(opts.get('baudrate', 115200))
    
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        os_log.log('PHY', f'UART listening on {port} @ {baudrate} baud')
        
        while True:
            try:
                if ser.in_waiting:
                    byte = ser.read(1)
                    if byte == b'\x02':  # STX
                        data = bytearray()
                        while True:
                            byte = ser.read(1)
                            if not byte:
                                break
                            if byte == b'\x03':  # ETX
                                if data and callback and callable(callback):
                                    callback(bytes(data), (port, 0))
                                break
                            data.extend(byte)
            except KeyboardInterrupt:
                break
            except Exception as e:
                os_log.err('PHY', 'UART_LISTEN', e, {'port': port})
    finally:
        ser.close()

