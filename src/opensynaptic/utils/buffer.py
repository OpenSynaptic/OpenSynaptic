from typing import Any


def as_readonly_view(payload: Any) -> memoryview:
    """Return a read-only memoryview for text/bytes-like payloads."""
    if isinstance(payload, memoryview):
        return payload.cast('B')
    if isinstance(payload, (bytes, bytearray)):
        return memoryview(payload)
    if isinstance(payload, str):
        return memoryview(payload.encode('utf-8'))
    try:
        return memoryview(payload)
    except TypeError:
        return memoryview(str(payload).encode('utf-8'))


def ensure_bytes(payload: Any) -> bytes:
    """Return bytes for socket/native boundaries."""
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode('utf-8')
    return as_readonly_view(payload).tobytes()


def payload_len(payload: Any) -> int:
    try:
        return len(payload)
    except Exception:
        return len(as_readonly_view(payload))


def zero_copy_enabled(config: Any) -> bool:
    if not isinstance(config, dict):
        return True
    settings = config.get('engine_settings', {}) if isinstance(config.get('engine_settings', {}), dict) else {}
    return bool(settings.get('zero_copy_transport', True))


