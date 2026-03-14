from opensynaptic.hardware_drivers.CAN import CAN_Driver

def send(payload, config):
    opts = config.get('physical_options', {}) if isinstance(config, dict) else {}
    can_id = int(opts.get('can_id', 291))
    CAN_Driver(can_id=can_id).segment_send(payload)
    return True
