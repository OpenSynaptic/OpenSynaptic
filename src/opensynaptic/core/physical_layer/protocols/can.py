from opensynaptic.hardware_drivers.CAN import CAN_Driver
from opensynaptic.utils import ensure_bytes, zero_copy_enabled

def send(payload, config):
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    can_id = int(opts.get('can_id', 291))
    wire_payload = payload if zero_copy_enabled(config) else ensure_bytes(payload)
    CAN_Driver(can_id=can_id).segment_send(wire_payload)
    return True
