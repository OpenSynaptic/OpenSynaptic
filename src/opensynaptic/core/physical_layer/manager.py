from opensynaptic.core.layered_protocol_manager import LayeredProtocolManager

class PhysicalLayerManager:
    _CANDIDATES = ('uart', 'rs485', 'can', 'lora', 'bluetooth')

    def __init__(self):
        self._impl = LayeredProtocolManager(layer_tag='PHY', module_prefix='opensynaptic.core.physical_layer.protocols', candidates=self._CANDIDATES, status_key='physical_status', config_key='physical_config')
        self.adapters = self._impl.adapters

    def set_config(self, config):
        self._impl.set_config(config)

    def discover(self):
        return self._impl.discover()

    def invalidate(self, name=None):
        return self._impl.invalidate(name)

    def refresh(self, name=None):
        return self._impl.refresh(name)

    def refresh_if_changed(self, name):
        return self._impl.refresh_if_changed(name)

    def get_adapter(self, name):
        return self._impl.get_adapter(name)

    def send(self, name, payload, config=None):
        return self._impl.send(name, payload, config=config, options_key='physical_options')
_PHYSICAL_MANAGER = PhysicalLayerManager()

def get_physical_layer_manager():
    if not _PHYSICAL_MANAGER.adapters:
        _PHYSICAL_MANAGER.discover()
    return _PHYSICAL_MANAGER
