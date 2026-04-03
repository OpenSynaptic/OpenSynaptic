from opensynaptic.hardware_drivers.LoRa import LoRaDriver
from opensynaptic.utils import to_wire_payload, os_log

def send(payload, config):
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    baudrate = int(opts.get('baudrate', 9600))
    timeout = int(opts.get('timeout', 2))
    driver = LoRaDriver(baudrate=baudrate, timeout=timeout)
    wire_payload = to_wire_payload(payload, config)
    result = driver.send(wire_payload)
    driver.close()
    return result is not None


def listen(config, callback):
    """
    Listen for incoming LoRa wireless packets.
    
    Args:
        config: dict with baudrate/timeout in physical_options
        callback: callable(data, addr) to handle received packets
    
    Returns:
        None (blocking listener)
    """
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    baudrate = int(opts.get('baudrate', 9600))
    timeout = int(opts.get('timeout', 2))
    
    try:
        driver = LoRaDriver(baudrate=baudrate, timeout=timeout)
        os_log.info('PHY', 'LORA_LISTEN_START', f'LoRa listening @ {baudrate} baud (timeout={timeout}s)', {'baudrate': baudrate, 'timeout': timeout})
        
        while True:
            try:
                data = driver.receive()
                if data and callback and callable(callback):
                    callback(data, ('LoRa', 0))
            except KeyboardInterrupt:
                break
            except Exception as e:
                os_log.err('PHY', 'LORA_LISTEN', e, {'baudrate': baudrate})
        driver.close()
    except Exception as e:
        os_log.err('PHY', 'LORA_INIT', e, {'baudrate': baudrate})

