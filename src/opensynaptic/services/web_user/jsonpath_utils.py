import json


def dotpath_get(payload, keypath):
    if not keypath:
        return payload
    current = payload
    for key in str(keypath).split('.'):
        if not isinstance(current, dict) or key not in current:
            raise KeyError(keypath)
        current = current[key]
    return current


def dotpath_set(payload, keypath, value):
    current = payload
    keys = [k for k in str(keypath).split('.') if k]
    if not keys:
        raise KeyError('key is required')
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def cast_value(raw, value_type):
    if value_type == 'int':
        return int(raw)
    if value_type == 'float':
        return float(raw)
    if value_type == 'bool':
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() not in ('0', 'false', 'no', 'off', '')
    if value_type == 'json':
        if isinstance(raw, str):
            return json.loads(raw)
        return raw
    return str(raw)

