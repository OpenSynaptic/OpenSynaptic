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
    APP_PROTOCOLS = {'mqtt'}
    TRANSPORT_PROTOCOLS = {'udp', 'tcp', 'quic', 'iwip', 'uip'}
    PHYSICAL_PROTOCOLS = {'uart', 'rs485', 'can', 'lora'}

    def __init__(self, master):
        self.master = master
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

    def _migrate_resource_maps(self):
        res = self.master.config.setdefault('RESOURCES', {})
        legacy = res.get('transporters_status', {}) if isinstance(res.get('transporters_status', {}), dict) else {}
        app_status = res.setdefault('application_status', {})
        transport_status = res.setdefault('transport_status', {})
        physical_status = res.setdefault('physical_status', {})
        changed = False
        for key, val in legacy.items():
            k = str(key).strip().lower()
            if k in self.APP_PROTOCOLS and k not in app_status:
                app_status[k] = bool(val)
                changed = True
            if k in self.TRANSPORT_PROTOCOLS and k not in transport_status:
                transport_status[k] = bool(val)
                changed = True
            if k in self.PHYSICAL_PROTOCOLS and k not in physical_status:
                physical_status[k] = bool(val)
                changed = True
        for k in self.APP_PROTOCOLS:
            if k not in app_status:
                app_status[k] = bool(legacy.get(k, False))
                changed = True
        for k in self.TRANSPORT_PROTOCOLS:
            if k not in transport_status:
                transport_status[k] = bool(legacy.get(k, True))
                changed = True
        for k in self.PHYSICAL_PROTOCOLS:
            if k not in physical_status:
                physical_status[k] = bool(legacy.get(k, False))
                changed = True
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
            self._transport_manager._impl.refresh_if_changed(key)
        for key in list(self._physical_manager.adapters.keys()):
            self._physical_manager._impl.refresh_if_changed(key)
        return True

    def refresh_protocol(self, medium):
        key = str(medium or '').strip().lower()
        if not key:
            return None
        refreshed = self._transport_manager.refresh(key)
        if refreshed:
            return _ManagerProxyDriver(self._transport_manager, key)
        refreshed = self._physical_manager.refresh(key)
        if refreshed:
            return _ManagerProxyDriver(self._physical_manager, key)
        return None

    def get_driver(self, medium):
        key = str(medium or '').strip().lower()
        if not key:
            return None
        app_driver = self._service.get_driver(key)
        if app_driver:
            return app_driver
        if self._transport_manager.get_adapter(key):
            return _ManagerProxyDriver(self._transport_manager, key)
        if self._physical_manager.get_adapter(key):
            return _ManagerProxyDriver(self._physical_manager, key)
        return None

    def dispatch_auto(self, packet):
        priority = self.master.config.get('RESOURCES', {}).get('priority_transporters', ['udp'])
        for medium in priority:
            driver = self.get_driver(medium)
            if driver and hasattr(driver, 'send'):
                if driver.send(packet, self.master.config):
                    return (True, medium)
        return (False, None)
