import importlib
import inspect

from opensynaptic.utils import os_log


PLUGIN_SPECS = {
    'tui': {
        'module': 'opensynaptic.services.tui',
        'class': 'TUIService',
        'defaults': {
            'enabled': True,
            'mode': 'manual',
            'default_section': 'identity',
            'default_interval': 2.0,
        },
    },
    'test_plugin': {
        'module': 'opensynaptic.services.test_plugin',
        'class': 'TestPlugin',
        'defaults': {
            'enabled': True,
            'mode': 'manual',
            'stress_workers': 8,
            'stress_total': 200,
            'stress_sources': 6,
            'stress_runtime': {
                'collector_mode': 'legacy',
                'collector_flush_every': 256,
                'pipeline_mode': 'legacy',
            },
        },
    },
    'web_user': {
        'module': 'opensynaptic.services.web_user',
        'class': 'WebUserService',
        'defaults': {
            'enabled': True,
            'mode': 'manual',
            'host': '127.0.0.1',
            'port': 8765,
            'auto_start': False,
            'management_enabled': True,
            'auth_enabled': False,
            'admin_token': '',
            'read_only': False,
            'writable_config_prefixes': [
                'RESOURCES.service_plugins',
                'RESOURCES.application_status',
                'RESOURCES.transport_status',
                'RESOURCES.physical_status',
                'RESOURCES.application_config',
                'RESOURCES.transport_config',
                'RESOURCES.physical_config',
                'engine_settings',
            ],
            'expose_sections': ['identity', 'transport', 'plugins', 'pipeline', 'config', 'users'],
            'ui_enabled': True,
            'ui_theme': 'router-dark',
            'ui_layout': 'sidebar',
            'ui_refresh_seconds': 3,
            'ui_compact': False,
        },
    },
    'dependency_manager': {
        'module': 'opensynaptic.services.dependency_manager',
        'class': 'DependencyManagerPlugin',
        'defaults': {
            'enabled': True,
            'mode': 'manual',
            'auto_repair': False,
        },
    },
    'env_guard': {
        'module': 'opensynaptic.services.env_guard.main',
        'class': 'EnvironmentGuardService',
        'defaults': {
            'enabled': True,
            'mode': 'manual',
            'auto_start': True,
            'auto_install': False,
            'max_history': 100,
            'install_commands': [],
            'resource_library_json_path': 'data/env_guard/resources.json',
            'status_json_path': 'data/env_guard/status.json',
        },
    },
    'port_forwarder': {
        'module': 'opensynaptic.services.port_forwarder',
        'class': 'PortForwarder',
        'defaults': {
            'enabled': True,
            'mode': 'auto',
            'rule_sets': [
                {
                    'name': 'default',
                    'description': 'Default forwarding rules',
                    'enabled': True,
                    'rules': [],
                }
            ],
            'persist_rules': True,
            'rules_file': 'data/port_forwarder_rules.json',
        },
    },
}

ALIASES = {
    'web-user': 'web_user',
    'deps': 'dependency_manager',
    'dependency': 'dependency_manager',
    'env-guard': 'env_guard',
    'port-forwarder': 'port_forwarder',
}


def normalize_plugin_name(name):
    key = str(name or '').strip().lower().replace('-', '_')
    return ALIASES.get(key, key)


def list_builtin_plugins():
    return sorted(PLUGIN_SPECS.keys())


def _deep_merge_missing(target, source):
    changed = False
    for key, value in (source or {}).items():
        if key not in target:
            target[key] = value
            changed = True
            continue
        if isinstance(target.get(key), dict) and isinstance(value, dict):
            if _deep_merge_missing(target[key], value):
                changed = True
    return changed


def ensure_plugin_defaults(config, plugin_name):
    key = normalize_plugin_name(plugin_name)
    spec = PLUGIN_SPECS.get(key)
    if spec is None:
        return False
    resources = config.setdefault('RESOURCES', {})
    service_cfg = resources.setdefault('service_plugins', {})
    plugin_cfg = service_cfg.setdefault(key, {})
    defaults = dict(spec.get('defaults', {}))
    changed = _deep_merge_missing(plugin_cfg, defaults)
    return changed


def get_plugin_config(config, plugin_name):
    key = normalize_plugin_name(plugin_name)
    resources = config.get('RESOURCES', {}) if isinstance(config.get('RESOURCES', {}), dict) else {}
    service_cfg = resources.get('service_plugins', {}) if isinstance(resources.get('service_plugins', {}), dict) else {}
    plugin_cfg = service_cfg.get(key, {}) if isinstance(service_cfg.get(key, {}), dict) else {}
    return plugin_cfg


def iter_enabled_plugins(config, auto_start_only=False):
    for key in list_builtin_plugins():
        plugin_cfg = get_plugin_config(config, key)
        if plugin_cfg.get('enabled', True) is False:
            continue
        if auto_start_only and (not bool(plugin_cfg.get('auto_start', False))):
            continue
        yield key, plugin_cfg


def sync_all_plugin_defaults(config):
    changed = False
    for key in PLUGIN_SPECS:
        if ensure_plugin_defaults(config, key):
            changed = True
    return changed


def _resolve_service_class(module, class_name=None):
    if class_name:
        cls = getattr(module, class_name, None)
        if inspect.isclass(cls):
            return cls
    for name in getattr(module, '__all__', []):
        obj = getattr(module, name, None)
        if inspect.isclass(obj):
            return obj
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj.__module__.startswith(module.__name__):
            return obj
    return None


def instantiate_plugin(plugin_name, node):
    key = normalize_plugin_name(plugin_name)
    spec = PLUGIN_SPECS.get(key)
    if spec:
        module_name = spec.get('module')
        class_name = spec.get('class')
    else:
        module_name = f'opensynaptic.services.{key}'
        class_name = None
    module = importlib.import_module(module_name)
    cls = _resolve_service_class(module, class_name=class_name)
    if cls is None:
        raise RuntimeError(f'No service class found in module: {module_name}')
    try:
        return cls(node)
    except TypeError:
        return cls()


def mount_plugin(node, plugin_name, mode='runtime'):
    key = normalize_plugin_name(plugin_name)
    svc = node.service_manager.get(key)
    if svc is not None:
        return svc
    svc = instantiate_plugin(key, node)
    node.service_manager.mount(key, svc, config=get_plugin_config(node.config, key), mode=mode)
    return svc


def ensure_and_mount_plugin(node, plugin_name, load=False, mode='runtime'):
    changed = ensure_plugin_defaults(node.config, plugin_name)
    if changed:
        node._save_config()
    svc = mount_plugin(node, plugin_name, mode=mode)
    if load:
        node.service_manager.load(normalize_plugin_name(plugin_name))
    return svc


def autoload_enabled_plugins(node, mode='runtime', auto_start_only=True):
    mounted = {}
    for key, _plugin_cfg in iter_enabled_plugins(node.config, auto_start_only=auto_start_only):
        try:
            mounted[key] = ensure_and_mount_plugin(node, key, load=True, mode=mode)
        except Exception as exc:
            os_log.err('SVC', 'AUTOLOAD', exc, {'plugin': key})
    return mounted


def safe_plugin_help():
    try:
        return list_builtin_plugins()
    except Exception as exc:
        os_log.err('SVC', 'REGISTRY', exc, {})
        return []


def get_plugin_cli_completion_meta(plugin_name):
    """Best-effort plugin CLI completion metadata.

    Returns dict[sub_cmd] = description.
    Plugins can optionally implement get_cli_completions(); fallback uses
    get_cli_commands() keys with empty descriptions.
    """
    key = normalize_plugin_name(plugin_name)
    spec = PLUGIN_SPECS.get(key)
    if spec:
        module_name = spec.get('module')
        class_name = spec.get('class')
    else:
        module_name = f'opensynaptic.services.{key}'
        class_name = None
    module = importlib.import_module(module_name)
    cls = _resolve_service_class(module, class_name=class_name)
    if cls is None:
        return {}
    try:
        svc = cls(None)
    except Exception:
        svc = cls()

    meta_fn = getattr(svc, 'get_cli_completions', None)
    if callable(meta_fn):
        raw = meta_fn()
        if isinstance(raw, dict):
            out = {}
            for k, v in raw.items():
                if isinstance(v, dict):
                    out[str(k)] = str(v.get('desc', ''))
                else:
                    out[str(k)] = str(v or '')
            return out

    cmds_fn = getattr(svc, 'get_cli_commands', None)
    if callable(cmds_fn):
        raw_cmds = cmds_fn()
        if isinstance(raw_cmds, dict):
            return {str(k): '' for k in raw_cmds.keys()}
    return {}


