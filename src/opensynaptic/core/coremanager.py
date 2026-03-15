import os
from pathlib import Path

from opensynaptic.core.loader import CorePluginRegistry
from opensynaptic.utils.paths import read_json


class CoreManager:
    """Discover, select, and lazy-load core plugins."""

    _IGNORE_DIRS = {'__pycache__', 'cache', 'transport_layer', 'physical_layer'}

    def __init__(self, base_package='opensynaptic.core', default_core='pycore'):
        self.base_package = base_package
        self.default_core = str(default_core or 'pycore').strip().lower()
        self.registry = CorePluginRegistry()
        self.config = {}
        self.active_core = None
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

    def set_active_core(self, name):
        key = str(name or '').strip().lower()
        if key not in self.available_cores():
            raise ValueError('unknown core plugin: {}'.format(name))
        self.active_core = key
        return self.active_core

    def get_active_core_name(self):
        return self.active_core or self._configured_core_name()

    def load_core(self, name=None):
        key = str(name or self.get_active_core_name()).strip().lower()
        plugin = self.registry.load(key)
        if plugin is None:
            raise RuntimeError('failed to load core plugin: {}'.format(key))
        self.active_core = key
        return plugin

    def list_symbols(self, name=None):
        plugin = self.load_core(name=name)
        symbols = plugin.get('symbols', {}) if isinstance(plugin, dict) else {}
        return sorted(symbols.keys())

    def get_symbol(self, symbol_name, name=None):
        plugin = self.load_core(name=name)
        symbols = plugin.get('symbols', {}) if isinstance(plugin, dict) else {}
        if symbol_name not in symbols:
            raise AttributeError('core plugin [{}] has no symbol [{}]'.format(self.get_active_core_name(), symbol_name))
        return symbols[symbol_name]

    def create_node(self, config_path=None, name=None, **kwargs):
        if config_path:
            self.set_config_path(config_path)
        if not name:
            # Always re-evaluate configured backend for node startup so
            # Config.json core_backend is respected even after prior loads.
            name = self._configured_core_name()
        node_cls = self.get_symbol('OpenSynaptic', name=name)
        return node_cls(config_path=config_path, **kwargs)


_CORE_MANAGER = CoreManager()


def get_core_manager():
    return _CORE_MANAGER

