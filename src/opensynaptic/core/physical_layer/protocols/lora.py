from opensynaptic.hardware_drivers.LoRa import LoRaDriver

def send(payload, config):
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    baudrate = int(opts.get('baudrate', 9600))
    timeout = int(opts.get('timeout', 2))
    driver = LoRaDriver(baudrate=baudrate, timeout=timeout)
    result = driver.send(payload)
    driver.close()
    return result is not None
