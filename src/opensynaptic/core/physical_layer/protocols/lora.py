from opensynaptic.hardware_drivers.LoRa import LoRaDriver
from opensynaptic.utils.buffer import ensure_bytes, zero_copy_enabled

def send(payload, config):
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    baudrate = int(opts.get('baudrate', 9600))
    timeout = int(opts.get('timeout', 2))
    driver = LoRaDriver(baudrate=baudrate, timeout=timeout)
    wire_payload = payload if zero_copy_enabled(config) else ensure_bytes(payload)
    result = driver.send(wire_payload)
    driver.close()
    return result is not None
