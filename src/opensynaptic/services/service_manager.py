import threading
import json
from opensynaptic.utils import os_log

class ServiceManager:
    """Mount point for internal service plugins and their runtime/config indexes."""

    def __init__(self, config=None, mode='runtime'):
        self.config = config or {}
        self.mode = mode
        self.mount_index = {}
        self.runtime_index = {}
        self.config_index = {}
        self._lock = threading.RLock()

    def _normalize_name(self, name):
        return str(name or '').strip().lower()

    def mount(self, name, service, config=None, mode=None):
        key = self._normalize_name(name)
        if not key:
            raise ValueError('service name is required')
        with self._lock:
            self.mount_index[key] = service
            self.config_index[key] = config or {}
            self.runtime_index[key] = {'enabled': bool(self._is_enabled(key)), 'mode': mode or self.mode, 'loaded': False}
        return service

    def get(self, name, default=None):
        key = self._normalize_name(name)
        return self.mount_index.get(key, default)

    def load(self, name):
        key = self._normalize_name(name)
        svc = self.mount_index.get(key)
        if not svc:
            return None
        state = self.runtime_index.get(key, {})
        if state.get('loaded'):
            return svc
        if hasattr(svc, 'auto_load'):
            svc.auto_load()
        state['loaded'] = True
        self.runtime_index[key] = state
        return svc

    def start_all(self):
        loaded = {}
        for name in list(self.mount_index.keys()):
            svc = self.load(name)
            if svc is not None:
                loaded[name] = svc
        return loaded

    def stop_all(self):
        for name, svc in list(self.mount_index.items()):
            try:
                if hasattr(svc, 'close'):
                    svc.close()
                elif hasattr(svc, 'shutdown'):
                    svc.shutdown()
            except Exception as exc:
                os_log.err('SVC', 'STOP', exc, {'service': name})
            state = self.runtime_index.get(name, {})
            state['loaded'] = False
            self.runtime_index[name] = state

    def snapshot(self):
        return {'mode': self.mode, 'mount_index': sorted(self.mount_index.keys()), 'runtime_index': self.runtime_index, 'config_index': self.config_index}

    def collect_cli_commands(self):
        """Return a mapping of {plugin_name: {sub_cmd: handler}} for every mounted service that exposes get_cli_commands()."""
        result = {}
        with self._lock:
            for name, svc in self.mount_index.items():
                if hasattr(svc, 'get_cli_commands'):
                    try:
                        cmds = svc.get_cli_commands()
                        if isinstance(cmds, dict):
                            result[name] = cmds
                    except Exception as exc:
                        os_log.err('SVC', 'CLI_COLLECT', exc, {'service': name})
        return result

    def collect_cli_completions(self):
        """Return {plugin_name: {sub_cmd: description}} completion metadata.

        Plugins may implement either:
        - get_cli_completions() -> dict[str, str|dict]
        - get_cli_commands() -> dict[str, callable]  (fallback with empty descriptions)
        """
        result = {}
        with self._lock:
            for name, svc in self.mount_index.items():
                try:
                    get_meta = getattr(svc, 'get_cli_completions', None)
                    if callable(get_meta):
                        meta = get_meta()
                        if isinstance(meta, dict):
                            # Normalize to sub_cmd -> description
                            normalized = {}
                            for k, v in meta.items():
                                if isinstance(v, dict):
                                    normalized[str(k)] = str(v.get('desc', ''))
                                else:
                                    normalized[str(k)] = str(v or '')
                            result[name] = normalized
                            continue
                    if hasattr(svc, 'get_cli_commands'):
                        cmds = svc.get_cli_commands()
                        if isinstance(cmds, dict):
                            result[name] = {str(k): '' for k in cmds.keys()}
                except Exception as exc:
                    os_log.err('SVC', 'CLI_COMPLETE', exc, {'service': name})
        return result

    def dispatch_plugin_cli(self, plugin_name, argv):
        """Route *argv* to the named plugin's CLI handler. Returns exit code (int)."""
        key = self._normalize_name(plugin_name)
        svc = self.mount_index.get(key)
        if svc is None:
            os_log.err('SVC', 'PLUGIN_CMD', ValueError(f'Plugin not mounted: {key}'), {'name': key})
            return 1
        if not hasattr(svc, 'get_cli_commands'):
            os_log.err('SVC', 'PLUGIN_CMD', ValueError(f'Plugin {key} has no CLI commands'), {'name': key})
            return 1
        try:
            cmds = svc.get_cli_commands()
            argv_tokens = [str(x) for x in list(argv or [])]
            sub_cmd = argv_tokens[0] if argv_tokens else ''
            handler = cmds.get(sub_cmd)
            if handler is None:
                print(f'Unknown sub-command "{sub_cmd}" for plugin "{key}". Available: {sorted(cmds.keys())}')
                return 1
            result = handler(argv_tokens[1:])
            # Conventional CLI handlers return int exit code.
            if isinstance(result, int):
                return int(result)
            # Dict payload handlers are treated as successful command responses.
            if isinstance(result, dict):
                print(json.dumps(result, ensure_ascii=False, default=str))
                return 0
            # Boolean/None fallback for older handlers.
            if result is None:
                return 0
            if isinstance(result, bool):
                return 0 if result else 1
            return 0
        except Exception as exc:
            os_log.err('SVC', 'PLUGIN_DISPATCH', exc, {'plugin': key, 'argv': list(argv or [])})
            return 1

    def _is_enabled(self, name):
        resources = self.config.get('RESOURCES', {})
        if name == 'transporters':
            status = resources.get('transporters_status', {})
            return any((bool(v) for v in status.values()))
        if name == 'db_engine':
            storage = self.config.get('storage', {})
            return bool(storage.get('sql', {}).get('enabled', False))
        service_plugins = resources.get('service_plugins', {}) if isinstance(resources.get('service_plugins', {}), dict) else {}
        normalized = str(name or '').strip().lower().replace('-', '_')
        plugin_cfg = service_plugins.get(normalized, {}) if isinstance(service_plugins.get(normalized, {}), dict) else {}
        if plugin_cfg:
            return bool(plugin_cfg.get('enabled', True))
        return True
