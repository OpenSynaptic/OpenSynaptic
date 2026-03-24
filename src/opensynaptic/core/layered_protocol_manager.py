import importlib
import os
from opensynaptic.utils import (
    LogMsg,
    os_log,
)
from opensynaptic.utils.buffer import to_wire_payload

class ProtocolAdapter:

    def __init__(self, name, module, mtime=0.0):
        self.name = name
        self.module = module
        self.mtime = mtime

    def send(self, payload, config):
        if not hasattr(self.module, 'send'):
            return False
        return bool(self.module.send(payload, config))

class LayeredProtocolManager:

    def __init__(self, layer_tag, module_prefix, candidates, status_key, config_key):
        self.layer_tag = layer_tag
        self.module_prefix = module_prefix
        self.candidates = tuple(candidates)
        self.status_key = status_key
        self.config_key = config_key
        self.adapters = {}
        self.config = {}

    def set_config(self, config):
        self.config = config or {}

    def _resources(self):
        return self.config.get('RESOURCES', {}) if isinstance(self.config, dict) else {}

    def _status_map(self):
        return self._resources().get(self.status_key, {})

    def _protocol_conf(self, name):
        cfg = self._resources().get(self.config_key, {})
        return cfg.get(name, {}) if isinstance(cfg, dict) else {}

    def _is_enabled(self, name):
        status = self._status_map()
        if not isinstance(status, dict):
            return True
        return bool(status.get(name, True))

    def invalidate(self, name=None):
        if name is None:
            for key in list(self.adapters.keys()):
                self.invalidate(key)
            return
        key = str(name or '').strip().lower()
        if not key:
            return
        if key in self.adapters:
            del self.adapters[key]
            os_log.log_with_const('info', LogMsg.PROTOCOL_INVALIDATED, layer=self.layer_tag, protocol=key)

    def refresh(self, name=None):
        if name is None:
            self.invalidate()
            return self.discover()
        key = str(name or '').strip().lower()
        if not key:
            return None
        self.invalidate(key)
        module = self._load_module(key)
        adapter = None
        if module:
            adapter = ProtocolAdapter(name=key, module=module, mtime=self._get_module_mtime(module))
            self.adapters[key] = adapter
        if adapter:
            os_log.log_with_const('info', LogMsg.PROTOCOL_REFRESHED, layer=self.layer_tag, protocol=key)
        return adapter

    def refresh_if_changed(self, name):
        key = str(name or '').strip().lower()
        adapter = self.adapters.get(key)
        if not adapter:
            return None
        current_mtime = self._get_module_mtime(adapter.module)
        if current_mtime and current_mtime > float(getattr(adapter, 'mtime', 0.0) or 0.0):
            return self.refresh(key)
        return adapter

    def discover(self):
        """Discover and load all candidate protocols from config status."""
        loaded = 0
        skipped = 0
        failed = 0
        for name in self.candidates:
            if not self._is_enabled(name):
                skipped += 1
                continue
            try:
                module = self._load_module(name)
                if module is None:
                    failed += 1
                    continue
                self.adapters[name] = ProtocolAdapter(name=name, module=module, mtime=self._get_module_mtime(module))
                loaded += 1
            except Exception as e:
                os_log.err(self.layer_tag, 'DISCOVER', e, {'protocol': name})
                failed += 1
        if loaded > 0:
            os_log.log_with_const('info', LogMsg.DRIVER_MOUNT, module=f'{self.layer_tag}:{loaded}', source=f'discover(skipped={skipped},failed={failed})')
        return self.adapters

    def get_adapter(self, name):
        key = str(name or '').strip().lower()
        if not key:
            return None
        if not self._is_enabled(key):
            return None
        existing = self.refresh_if_changed(key)
        if existing:
            return existing
        if key not in self.adapters:
            module = self._load_module(key)
            if module:
                self.adapters[key] = ProtocolAdapter(name=key, module=module, mtime=self._get_module_mtime(module))
        return self.adapters.get(key)

    def send(self, name, payload, config=None, options_key=None):
        if config is not None:
            self.set_config(config)
        adapter = self.get_adapter(name)
        if not adapter:
            return False
        try:
            merged = self._build_merged_config(name, config=config, options_key=options_key)
            wire_payload = self._to_wire_payload(payload, merged)
            return adapter.send(wire_payload, merged)
        except Exception as exc:
            os_log.err(self.layer_tag, 'SEND', exc, {'protocol': name})
            return False

    def _build_merged_config(self, name, config=None, options_key=None):
        merged = {}
        merged.update(config or {} if isinstance(config, dict) else self.config)
        if options_key:
            merged[options_key] = self._protocol_conf(str(name).lower())
        return merged

    def _to_wire_payload(self, payload, merged_config):
        return to_wire_payload(payload, merged_config)

    def _load_module(self, name):
        """Load and validate a protocol module."""
        try:
            module_path = '{}.{}'.format(self.module_prefix, name)
            module = importlib.import_module(module_path)
            
            # Check if protocol declares itself as unsupported
            if hasattr(module, 'is_supported') and not module.is_supported():
                os_log.log_with_const('info', LogMsg.DRIVER_SLEEP, module=name)
                return None
            
            # Verify send function exists
            if not hasattr(module, 'send'):
                os_log.err(self.layer_tag, 'LOAD', f'Missing send() in {module_path}', {'protocol': name})
                return None
            
            return module
        except ModuleNotFoundError as e:
            os_log.err(self.layer_tag, 'NOT_FOUND', e, {'protocol': name, 'module_path': '{}.{}'.format(self.module_prefix, name)})
            return None
        except Exception as e:
            os_log.err(self.layer_tag, 'LOAD', e, {'protocol': name})
            return None

    def _get_module_mtime(self, module):
        try:
            module_file = getattr(module, '__file__', None)
            if not module_file:
                return 0.0
            return os.path.getmtime(module_file)
        except Exception:
            return 0.0
