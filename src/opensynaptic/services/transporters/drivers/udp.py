from opensynaptic.core.transport_layer import get_transport_layer_manager

def send(packet, config):
    return get_transport_layer_manager().send('udp', packet, config)
