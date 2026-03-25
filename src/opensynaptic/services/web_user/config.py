from .jsonpath_utils import dotpath_get, dotpath_set, cast_value


class ConfigFacade:
    def __init__(self, service):
        self.service = service

    def config_ref(self):
        if self.service.node and isinstance(getattr(self.service.node, 'config', None), dict):
            return self.service.node.config
        return {}

    def get_payload(self, key=None):
        cfg = self.config_ref()
        if not key:
            return {'ok': True, 'config': cfg}
        return {'ok': True, 'key': key, 'value': dotpath_get(cfg, key)}

    def set_payload(self, key, value, value_type='json'):
        if not self.service._is_key_writable(key):
            return False, {'error': 'write blocked by writable_config_prefixes', 'key': key}
        cfg = self.config_ref()
        typed = cast_value(value, value_type)
        old_val = None
        try:
            old_val = dotpath_get(cfg, key)
        except Exception:
            old_val = None
        dotpath_set(cfg, key, typed)
        saver = getattr(self.service.node, '_save_config', None)
        if callable(saver):
            saver()
        return True, {'ok': True, 'key': key, 'old': old_val, 'new': typed}

