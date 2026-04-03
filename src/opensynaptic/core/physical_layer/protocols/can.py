from opensynaptic.hardware_drivers.CAN import CAN_Driver
from opensynaptic.utils import to_wire_payload, os_log

def send(payload, config):
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    can_id = int(opts.get('can_id', 291))
    wire_payload = to_wire_payload(payload, config)
    CAN_Driver(can_id=can_id).segment_send(wire_payload)
    return True


def listen(config, callback):
    """
    Listen for incoming CAN bus messages.
    
    Args:
        config: dict with can_id in physical_options
        callback: callable(data, addr) to handle received packets
    
    Returns:
        None (blocking listener)
    """
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    can_id = int(opts.get('can_id', 291))
    
    try:
        driver = CAN_Driver(can_id=can_id)
        os_log.info('PHY', 'CAN_LISTEN_START', f'CAN listening on ID 0x{can_id:03X}', {'can_id': can_id})
        
        while True:
            try:
                data = driver.receive()
                if data and callback and callable(callback):
                    callback(data, (f'CAN:0x{can_id:03X}', 0))
            except KeyboardInterrupt:
                break
            except Exception as e:
                os_log.err('PHY', 'CAN_LISTEN', e, {'can_id': can_id})
    except Exception as e:
        os_log.err('PHY', 'CAN_INIT', e, {'can_id': can_id})

