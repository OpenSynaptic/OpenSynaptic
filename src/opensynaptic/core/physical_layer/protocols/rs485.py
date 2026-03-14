from opensynaptic.hardware_drivers.RS485 import RS485_Driver

def send(payload, config):
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    port = opts.get('port', 'COM1')
    baudrate = int(opts.get('baudrate', 9600))
    RS485_Driver(port=port, baudrate=baudrate).send(payload)
    return True
