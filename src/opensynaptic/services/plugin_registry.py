import importlib
import inspect

from opensynaptic.utils.logger import os_log


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
}

ALIASES = {
    'web-user': 'web_user',
    'deps': 'dependency_manager',
    'dependency': 'dependency_manager',
    'env-guard': 'env_guard',
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
    node.service_manager.mount(key, svc, config={}, mode=mode)
    return svc


def ensure_and_mount_plugin(node, plugin_name, load=False, mode='runtime'):
    changed = ensure_plugin_defaults(node.config, plugin_name)
    if changed:
        node._save_config()
    svc = mount_plugin(node, plugin_name, mode=mode)
    if load:
        node.service_manager.load(normalize_plugin_name(plugin_name))
    return svc


def safe_plugin_help():
    try:
        return list_builtin_plugins()
    except Exception as exc:
        os_log.err('SVC', 'REGISTRY', exc, {})
        return []

