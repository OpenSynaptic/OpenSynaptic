from opensynaptic.hardware_drivers.RS485 import RS485_Driver
from opensynaptic.utils.buffer import ensure_bytes, zero_copy_enabled

def send(payload, config):
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    port = opts.get('port', 'COM1')
    baudrate = int(opts.get('baudrate', 9600))
    wire_payload = payload if zero_copy_enabled(config) else ensure_bytes(payload)
    RS485_Driver(port=port, baudrate=baudrate).send(wire_payload)
    return True
