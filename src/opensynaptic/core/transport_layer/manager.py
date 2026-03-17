from opensynaptic.core.layered_protocol_manager import LayeredProtocolManager

class TransportLayerManager:
    _CANDIDATES = ('udp', 'tcp', 'quic', 'iwip', 'uip')

    def __init__(self):
        self._impl = LayeredProtocolManager(layer_tag='L4', module_prefix='opensynaptic.core.transport_layer.protocols', candidates=self._CANDIDATES, status_key='transport_status', config_key='transport_config')
        self.adapters = self._impl.adapters

    def set_config(self, config):
        self._impl.set_config(config)

    def discover(self):
        return self._impl.discover()

    def invalidate(self, name=None):
        return self._impl.invalidate(name)

    def refresh(self, name=None):
        return self._impl.refresh(name)

    def get_adapter(self, name):
        return self._impl.get_adapter(name)

    def send(self, name, payload, config=None):
        return self._impl.send(name, payload, config=config, options_key='transport_options')
_TRANSPORT_MANAGER = TransportLayerManager()

def get_transport_layer_manager():
    if not _TRANSPORT_MANAGER.adapters:
        _TRANSPORT_MANAGER.discover()
    return _TRANSPORT_MANAGER
