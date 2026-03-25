def friendly_label(path):
    leaf = str(path or '').split('.')[-1]
    return leaf.replace('_', ' ').strip().title() or str(path)


def infer_value_type(value):
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, int) and (not isinstance(value, bool)):
        return 'int'
    if isinstance(value, float):
        return 'float'
    if isinstance(value, str):
        return 'str'
    return 'json'


def field_annotation(path, annotations):
    exact = (annotations or {}).get(path)
    if exact:
        return exact
    leaf = str(path or '').split('.')[-1]
    if leaf.endswith('enabled'):
        return 'Toggle switch for this feature.'
    if leaf.endswith('port'):
        return 'Network or device port value.'
    if leaf.endswith('host'):
        return 'Target hostname or bind address.'
    if leaf.endswith('seconds'):
        return 'Duration in seconds.'
    return 'Auto-generated from current config value type.'


def flatten_option_fields(path, value, fields, is_key_writable, annotations):
    if isinstance(value, dict):
        for key in sorted(value.keys()):
            next_path = '{}.{}'.format(path, key) if path else str(key)
            flatten_option_fields(next_path, value.get(key), fields, is_key_writable, annotations)
        return
    field_type = infer_value_type(value)
    fields.append({
        'key': path,
        'label': friendly_label(path),
        'description': field_annotation(path, annotations),
        'type': field_type,
        'value': value,
        'writable': bool(is_key_writable(path)),
        'choices': [True, False] if field_type == 'bool' else None,
    })


def category_title(prefix):
    titles = {
        'RESOURCES.service_plugins': 'Service Plugins',
        'RESOURCES.application_status': 'Application Drivers',
        'RESOURCES.transport_status': 'Transport Drivers',
        'RESOURCES.physical_status': 'Physical Drivers',
        'RESOURCES.application_config': 'Application Config',
        'RESOURCES.transport_config': 'Transport Config',
        'RESOURCES.physical_config': 'Physical Config',
        'engine_settings': 'Engine Settings',
        'security_settings.id_lease': 'ID Lease Policy',
    }
    return titles.get(prefix, friendly_label(prefix))

