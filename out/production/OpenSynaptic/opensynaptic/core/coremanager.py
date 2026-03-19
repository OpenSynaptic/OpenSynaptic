import os
from pathlib import Path

from opensynaptic.core.loader import CorePluginRegistry
from opensynaptic.utils import read_json


class CoreManager:
    """Discover, select, and lazy-load core plugins."""

    _IGNORE_DIRS = {'__pycache__', 'cache', 'transport_layer', 'physical_layer'}

    def __init__(self, base_package='opensynaptic.core', default_core='pycore'):
        self.base_package = base_package
        self.default_core = str(default_core or 'pycore').strip().lower()
        self.registry = CorePluginRegistry()
        self.config = {}
        self.active_core = None
        self._last_load_trace = {}
        self.discover_cores()

    def set_config(self, config=None):
        self.config = config or {}
        return self.config

    def set_config_path(self, config_path=None):
        if not config_path:
            return self.config
        cfg = read_json(config_path) if Path(config_path).exists() else {}
        return self.set_config(cfg)

    def discover_cores(self):
        base_dir = Path(__file__).resolve().parent
        for child in base_dir.iterdir():
            if not child.is_dir():
                continue
            if child.name in self._IGNORE_DIRS or child.name.startswith('_'):
                continue
            if not (child / '__init__.py').exists():
                continue
            self.registry.register(child.name, '{}.{}'.format(self.base_package, child.name))
        return self.registry.names()

    def available_cores(self):
        return self.registry.names()

    def _configured_core_name(self):
        env_name = str(os.getenv('OPENSYNAPTIC_CORE', '')).strip().lower()
        if env_name:
            return env_name
        settings = self.config.get('engine_settings', {}) if isinstance(self.config, dict) else {}
        cfg_name = str(settings.get('core_backend', '')).strip().lower()
        if cfg_name:
            return cfg_name
        return self.default_core

    def _core_candidates(self, preferred=None):
        available = self.available_cores()
        seen = set()
        ordered = []

        def _push(name):
            key = str(name or '').strip().lower()
            if not key or key in seen:
                return
            seen.add(key)
            ordered.append(key)

        _push(preferred)
        _push(self.active_core)
        _push(self._configured_core_name())
        _push(self.default_core)
        for name in available:
            _push(name)
        return [name for name in ordered if name in available]

    @staticmethod
    def _plugin_symbols(plugin):
        if not isinstance(plugin, dict):
            return {}
        symbols = plugin.get('symbols', {})
        return symbols if isinstance(symbols, dict) else {}

    def _is_plugin_healthy(self, plugin):
        symbols = self._plugin_symbols(plugin)
        return 'OpenSynaptic' in symbols

    def _plugin_capabilities(self, plugin):
        if not isinstance(plugin, dict):
            return {}
        # Keep capability reporting generic; do not assume a specific core name.
        return {
            'name': plugin.get('name'),
            'kind': plugin.get('kind'),
            'backend': plugin.get('backend'),
            'symbol_count': len(self._plugin_symbols(plugin)),
            'flags': {
                key: value for key, value in plugin.items()
                if key not in ('symbols', 'name', 'kind', 'backend') and isinstance(value, (bool, int, float, str))
            },
        }

    def get_core_status(self, requested=None):
        requested_key = str(requested or '').strip().lower() or None
        candidates = self._core_candidates(preferred=requested_key)
        resolved = self.active_core if self.active_core in candidates else (candidates[0] if candidates else None)
        return {
            'requested': requested_key,
            'resolved': resolved,
            'active': self.active_core,
            'configured': self._configured_core_name(),
            'available': self.available_cores(),
            'candidates': candidates,
            'last_load_trace': dict(self._last_load_trace),
        }

    def set_active_core(self, name):
        key = str(name or '').strip().lower()
        if key not in self.available_cores():
            raise ValueError('unknown core plugin: {}'.format(name))
        self.active_core = key
        return self.active_core

    def get_active_core_name(self):
        candidates = self._core_candidates(preferred=self.active_core)
        if candidates:
            return candidates[0]
        return self._configured_core_name()

    def load_core(self, name=None):
        requested = str(name or '').strip().lower() or self.get_active_core_name()
        candidates = self._core_candidates(preferred=requested)
        if not candidates:
            raise RuntimeError('no core plugins discovered')

        errors = {}
        for key in candidates:
            try:
                plugin = self.registry.load(key)
                if plugin is None:
                    errors[key] = 'empty core plugin payload'
                    continue
                if not self._is_plugin_healthy(plugin):
                    errors[key] = 'missing required symbol: OpenSynaptic'
                    continue
                self.active_core = key
                self._last_load_trace = {
                    'requested': requested,
                    'resolved': key,
                    'fallback_used': key != requested,
                    'candidates': candidates,
                    'capabilities': self._plugin_capabilities(plugin),
                    'errors': errors,
                }
                return plugin
            except Exception as exc:
                errors[key] = str(exc)
                continue

        self._last_load_trace = {
            'requested': requested,
            'resolved': None,
            'fallback_used': False,
            'candidates': candidates,
            'errors': errors,
        }
        raise RuntimeError('failed to load core plugin [{}], fallback exhausted: {}'.format(requested, errors))

    def list_symbols(self, name=None):
        plugin = self.load_core(name=name)
        symbols = self._plugin_symbols(plugin)
        return sorted(symbols.keys())

    def get_symbol(self, symbol_name, name=None):
        plugin = self.load_core(name=name)
        symbols = self._plugin_symbols(plugin)
        if symbol_name not in symbols:
            raise AttributeError('core plugin [{}] has no symbol [{}]'.format(self.get_active_core_name(), symbol_name))
        return symbols[symbol_name]

    def create_node(self, config_path=None, name=None, **kwargs):
        if config_path:
            self.set_config_path(config_path)
        if not name:
            # Resolve the best available backend with fallback support.
            name = self.get_active_core_name()
        node_cls = self.get_symbol('OpenSynaptic', name=name)
        return node_cls(config_path=config_path, **kwargs)


_CORE_MANAGER = CoreManager()


def get_core_manager():
    return _CORE_MANAGER

