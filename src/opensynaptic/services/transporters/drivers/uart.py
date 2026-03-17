from opensynaptic.core.physical_layer import get_physical_layer_manager

def send(payload, config):
    return get_physical_layer_manager().send('uart', payload, config)
