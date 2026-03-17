from opensynaptic.core.transport_layer import get_transport_layer_manager

def send(payload, config):
    return get_transport_layer_manager().send('quic', payload, config)
