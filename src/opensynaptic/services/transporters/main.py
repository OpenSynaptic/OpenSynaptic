import importlib
import pkgutil
from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg
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
        return bool(send_fn(payload, merged))

class TransporterService:
    """Service plugin responsible for transporter driver discovery and dispatch."""
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
        if 'RESOURCES' not in self.master.config:
            self.master.config['RESOURCES'] = {}
        resources = self.master.config['RESOURCES']
        status_map = resources.get('application_status', {})
        resources['application_status'] = status_map
        resources.setdefault('application_config', {})
        dirty = False
        for _, module_name, is_pkg in pkgutil.iter_modules(drivers.__path__):
            if is_pkg or module_name.startswith('_'):
                continue
            key = module_name.lower()
            if key not in self.APP_LAYER_DRIVERS:
                continue
            if key not in status_map:
                status_map[key] = False
                dirty = True
                os_log.log_with_const('info', LogMsg.NEW_DRIVER_REGISTERED, module=module_name)
            if status_map.get(key) is True:
                module = self._lazy_load_driver(key)
                if module is None and status_map.get(key):
                    status_map[key] = False
                    dirty = True
            else:
                os_log.log_with_const('info', LogMsg.DRIVER_SLEEP, module=module_name)
        if dirty:
            merged = resources.get('transporters_status', {})
            if not isinstance(merged, dict):
                merged = {}
            merged.update(status_map)
            resources['transporters_status'] = merged
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
