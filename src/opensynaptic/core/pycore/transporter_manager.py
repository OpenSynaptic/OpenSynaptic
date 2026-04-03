from opensynaptic.services import ServiceManager
from opensynaptic.services.transporters import TransporterService
from opensynaptic.core.transport_layer import get_transport_layer_manager
from opensynaptic.core.physical_layer import get_physical_layer_manager

class _ManagerProxyDriver:

    def __init__(self, manager, protocol_name):
        self._manager = manager
        self._name = protocol_name

    def send(self, payload, config):
        return self._manager.send(self._name, payload, config)

class TransporterManager:
    APP_PROTOCOLS = {'mqtt', 'matter', 'zigbee'}
    TRANSPORT_PROTOCOLS = {'udp', 'tcp', 'quic', 'iwip', 'uip'}
    PHYSICAL_PROTOCOLS = {'uart', 'rs485', 'can', 'lora', 'bluetooth'}

    def __init__(self, master):
        self.master = master
        self._proxy_cache = {}
        self._migrate_resource_maps()
        self._service_manager = getattr(master, 'service_manager', None)
        if not self._service_manager:
            self._service_manager = ServiceManager(config=master.config, mode='runtime')
            master.service_manager = self._service_manager
        self._service = self._service_manager.get('transporters')
        if not self._service:
            self._service = TransporterService(master)
            self._service_manager.mount('transporters', self._service, config=master.config.get('RESOURCES', {}).get('application_status', {}), mode='runtime')
        self.active_transporters = self._service.active_transporters
        self._transport_manager = get_transport_layer_manager()
        self._physical_manager = get_physical_layer_manager()
        self._transport_manager.set_config(master.config)
        self._physical_manager.set_config(master.config)

    def _get_or_create_proxy(self, manager, key):
        cache_key = (id(manager), key)
        proxy = self._proxy_cache.get(cache_key)
        if proxy is None:
            proxy = _ManagerProxyDriver(manager, key)
            self._proxy_cache[cache_key] = proxy
        return proxy

    def _migrate_resource_maps(self):
        res = self.master.config.setdefault('RESOURCES', {})
        legacy = res.get('transporters_status', {}) if isinstance(res.get('transporters_status', {}), dict) else {}
        app_status = res.setdefault('application_status', {})
        transport_status = res.setdefault('transport_status', {})
        physical_status = res.setdefault('physical_status', {})
        changed = False

        def _pull_from_legacy(protocol_set, target_map):
            nonlocal changed
            for key, val in legacy.items():
                k = str(key).strip().lower()
                if k in protocol_set and k not in target_map:
                    target_map[k] = bool(val)
                    changed = True

        def _apply_defaults(protocol_set, target_map, default_value):
            nonlocal changed
            for k in protocol_set:
                if k not in target_map:
                    target_map[k] = bool(legacy.get(k, default_value))
                    changed = True

        _pull_from_legacy(self.APP_PROTOCOLS, app_status)
        _pull_from_legacy(self.TRANSPORT_PROTOCOLS, transport_status)
        _pull_from_legacy(self.PHYSICAL_PROTOCOLS, physical_status)

        _apply_defaults(self.APP_PROTOCOLS, app_status, False)
        _apply_defaults(self.TRANSPORT_PROTOCOLS, transport_status, True)
        _apply_defaults(self.PHYSICAL_PROTOCOLS, physical_status, False)

        res.setdefault('application_config', {})
        res.setdefault('transport_config', {})
        res.setdefault('physical_config', {})
        merged = {}
        merged.update(app_status)
        merged.update(transport_status)
        merged.update(physical_status)
        if res.get('transporters_status') != merged:
            res['transporters_status'] = merged
            changed = True
        if changed and hasattr(self.master, '_save_config'):
            self.master._save_config()

    def auto_load(self):
        self._transport_manager.set_config(self.master.config)
        self._physical_manager.set_config(self.master.config)
        self._transport_manager.invalidate()
        self._physical_manager.invalidate()
        self._service.auto_load()
        self._transport_manager.discover()
        self._physical_manager.discover()
        return self.active_transporters

    def runtime_tick(self):
        self._transport_manager.set_config(self.master.config)
        self._physical_manager.set_config(self.master.config)
        for key in list(self._transport_manager.adapters.keys()):
            self._transport_manager.refresh_if_changed(key)
        for key in list(self._physical_manager.adapters.keys()):
            self._physical_manager.refresh_if_changed(key)
        return True

    def _normalize_medium(self, medium):
        return str(medium or '').strip().lower()

    def refresh_protocol(self, medium):
        key = self._normalize_medium(medium)
        if not key:
            return None
        refreshed = self._transport_manager.refresh(key)
        if refreshed:
            return self._get_or_create_proxy(self._transport_manager, key)
        refreshed = self._physical_manager.refresh(key)
        if refreshed:
            return self._get_or_create_proxy(self._physical_manager, key)
        return None

    def get_driver(self, medium):
        key = self._normalize_medium(medium)
        if not key:
            return None
        app_driver = self._service.get_driver(key)
        if app_driver:
            return app_driver
        if key in self.TRANSPORT_PROTOCOLS and self._transport_manager.get_adapter(key):
            return self._get_or_create_proxy(self._transport_manager, key)
        if key in self.PHYSICAL_PROTOCOLS and self._physical_manager.get_adapter(key):
            return self._get_or_create_proxy(self._physical_manager, key)
        return None

    def dispatch_auto(self, packet):
        priority = self.master.config.get('RESOURCES', {}).get('priority_transporters', ['udp'])
        for medium in priority:
            driver = self.get_driver(medium)
            if driver and hasattr(driver, 'send'):
                if driver.send(packet, self.master.config):
                    return (True, medium)
        return (False, None)
