from opensynaptic.hardware_drivers.RS485 import RS485_Driver
from opensynaptic.utils import to_wire_payload, os_log

def send(payload, config):
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    port = opts.get('port', 'COM1')
    baudrate = int(opts.get('baudrate', 9600))
    wire_payload = to_wire_payload(payload, config)
    RS485_Driver(port=port, baudrate=baudrate).send(wire_payload)
    return True


def listen(config, callback):
    """
    Listen for incoming RS485 packets (half-duplex mode).
    
    Args:
        config: dict with port/baudrate in physical_options
        callback: callable(data, addr) to handle received packets
    
    Returns:
        None (blocking listener)
    """
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    port = opts.get('port', 'COM1')
    baudrate = int(opts.get('baudrate', 9600))
    
    try:
        driver = RS485_Driver(port=port, baudrate=baudrate)
        os_log.log('PHY', f'RS485 listening on {port} @ {baudrate} baud')
        
        while True:
            try:
                data = driver.receive()
                if data and callback and callable(callback):
                    callback(data, (port, 0))
            except KeyboardInterrupt:
                break
            except Exception as e:
                os_log.err('PHY', 'RS485_LISTEN', e, {'port': port})
    except Exception as e:
        os_log.err('PHY', 'RS485_INIT', e, {'port': port})

