import importlib
import pkgutil
from opensynaptic.utils import (
    os_log,
    LogMsg,
)
from opensynaptic.utils.buffer import to_wire_payload
from opensynaptic.services.transporters import drivers

class _AppProxyDriver:

    def __init__(self, name, module, service):
        self._name = name
        self._module = module
        self._service = service

    def send(self, payload, config):
        merged = {}
        if isinstance(config, dict):
            merged.update(config)
        merged['application_options'] = self._service.get_protocol_config(self._name)
        send_fn = getattr(self._module, 'send', None)
        if not send_fn:
            return False
        wire_payload = to_wire_payload(payload, merged)
        return bool(send_fn(wire_payload, merged))

class TransporterService:
    """
    Application-layer (L7) transporter service.
    Manages only application-layer drivers (MQTT).
    
    Transport & Physical layer drivers are handled by LayeredProtocolManager
    in src/opensynaptic/core/transport_layer and physical_layer.
    """
    APP_LAYER_DRIVERS = {'mqtt'}

    def __init__(self, master):
        self.master = master
        self.active_transporters = {}

    def get_protocol_config(self, key):
        resources = self.master.config.get('RESOURCES', {})
        app_cfg = resources.get('application_config', {})
        if not isinstance(app_cfg, dict):
            return {}
        return app_cfg.get(key, {}) if isinstance(app_cfg.get(key, {}), dict) else {}

    def auto_load(self):
        """Discover and load application-layer drivers (only MQTT)."""
        if 'RESOURCES' not in self.master.config:
            self.master.config['RESOURCES'] = {}
        resources = self.master.config['RESOURCES']
        status_map = resources.get('application_status', {})
        resources['application_status'] = status_map
        resources.setdefault('application_config', {})
        dirty = False
        
        # Discover only app-layer drivers from drivers/ folder
        for _, module_name, is_pkg in pkgutil.iter_modules(drivers.__path__):
            if is_pkg or module_name.startswith('_'):
                continue
            key = module_name.lower()
            # Only process app-layer drivers
            if key not in self.APP_LAYER_DRIVERS:
                continue
            # Register new drivers with disabled default
            if key not in status_map:
                status_map[key] = False
                dirty = True
                os_log.log_with_const('info', LogMsg.NEW_DRIVER_REGISTERED, module=module_name)
            # Load if enabled
            if status_map.get(key) is True:
                module = self._lazy_load_driver(key)
                if module is None and status_map.get(key):
                    status_map[key] = False
                    dirty = True
            else:
                os_log.log_with_const('info', LogMsg.DRIVER_SLEEP, module=module_name)
        
        if dirty:
            self.master._save_config()
        return self.active_transporters

    def _normalize_medium(self, medium):
        if not medium:
            return ''
        key = str(medium).strip().lower()
        if key.startswith('transport_'):
            key = key[len('transport_'):]
        return key

    def _lazy_load_driver(self, key):
        if not key:
            return None
        if key not in self.APP_LAYER_DRIVERS:
            return None
        if key in self.active_transporters:
            return self.active_transporters[key]
        try:
            module = importlib.import_module('opensynaptic.services.transporters.drivers.{}'.format(key))
            self.active_transporters[key] = _AppProxyDriver(key, module, self)
            os_log.log_with_const('info', LogMsg.DRIVER_ACTIVATED, module=key)
            return self.active_transporters[key]
        except Exception as e:
            os_log.err('TRN', 'LOAD', e, {'module': key})
            return None

    def get_driver(self, medium):
        key = self._normalize_medium(medium)
        if not key:
            return None
        driver = self.active_transporters.get(key)
        if driver:
            return driver
        return self._lazy_load_driver(key)

    def dispatch_auto(self, packet):
        priority = self.master.config.get('RESOURCES', {}).get('priority_transporters', ['mqtt'])
        for medium in priority:
            driver = self.get_driver(medium)
            if driver and hasattr(driver, 'send'):
                if hasattr(driver, 'is_ready') and (not driver.is_ready(self.master.config)):
                    continue
                success = driver.send(packet, self.master.config)
                if success:
                    return (True, medium)
        return (False, None)
