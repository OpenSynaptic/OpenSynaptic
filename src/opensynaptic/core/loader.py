import importlib
import threading


class CorePluginRegistry:
    """Lazy registry for core plugins."""

    def __init__(self):
        self._entries = {}
        self._plugins = {}
        self._lock = threading.RLock()

    def _normalize_name(self, name):
        return str(name or '').strip().lower()

    def register(self, name, module_path):
        key = self._normalize_name(name)
        if not key:
            raise ValueError('core plugin name is required')
        with self._lock:
            self._entries[key] = str(module_path)
            self._plugins.pop(key, None)

    def names(self):
        with self._lock:
            return sorted(self._entries.keys())

    def clear(self, name=None):
        with self._lock:
            if name is None:
                self._plugins.clear()
                return
            key = self._normalize_name(name)
            self._plugins.pop(key, None)

    def load(self, name):
        key = self._normalize_name(name)
        if not key:
            return None
        with self._lock:
            cached = self._plugins.get(key)
            if cached is not None:
                return cached
            module_path = self._entries.get(key)
        if not module_path:
            return None
        module = importlib.import_module(module_path)
        factory = getattr(module, 'get_core_plugin', None)
        plugin = factory() if callable(factory) else getattr(module, 'CORE_PLUGIN', None)
        if not isinstance(plugin, dict):
            raise RuntimeError('Invalid core plugin module: {}'.format(module_path))
        with self._lock:
            self._plugins[key] = plugin
        return plugin

