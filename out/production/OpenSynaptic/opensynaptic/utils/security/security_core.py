import ctypes

from opensynaptic.utils.c.native_loader import require_native_library


CRC8_POLY = 7
CRC16_POLY = 4129
CRC16_INIT = 65535

_LIB = None
_CONFIGURED = False


def _lib():
    global _LIB, _CONFIGURED
    if _LIB is None:
        _LIB = require_native_library('os_security')
    if not _CONFIGURED:
        _LIB.os_crc8.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_size_t, ctypes.c_ushort, ctypes.c_ubyte]
        _LIB.os_crc8.restype = ctypes.c_ubyte
        _LIB.os_crc16_ccitt.argtypes = [ctypes.POINTER(ctypes.c_ubyte), ctypes.c_size_t, ctypes.c_ushort, ctypes.c_ushort]
        _LIB.os_crc16_ccitt.restype = ctypes.c_ushort
        _LIB.os_xor_payload.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_size_t,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_ubyte),
        ]
        _LIB.os_xor_payload.restype = None
        _LIB.os_derive_session_key.argtypes = [ctypes.c_ulonglong, ctypes.c_ulonglong, ctypes.POINTER(ctypes.c_ubyte)]
        _LIB.os_derive_session_key.restype = None
        _CONFIGURED = True
    return _LIB


def _as_u8_array(data):
    if data is None:
        return b'', (ctypes.c_ubyte * 0)()
    if isinstance(data, bytes):
        arr_t = ctypes.c_ubyte * len(data)
        return data, arr_t.from_buffer_copy(data)
    if isinstance(data, bytearray):
        arr_t = ctypes.c_ubyte * len(data)
        return data, arr_t.from_buffer(data)
    if isinstance(data, memoryview):
        view = data.cast('B') if data.format != 'B' else data
        if view.readonly:
            arr_t = ctypes.c_ubyte * len(view)
            return view, arr_t.from_buffer_copy(view)
        arr_t = ctypes.c_ubyte * len(view)
        return view, arr_t.from_buffer(view)
    raw = bytes(data)
    arr_t = ctypes.c_ubyte * len(raw)
    return raw, arr_t.from_buffer_copy(raw)


def crc8(data, poly=CRC8_POLY, init=0):
    lib = _lib()
    raw, arr = _as_u8_array(data)
    ptr = ctypes.cast(arr, ctypes.POINTER(ctypes.c_ubyte)) if raw else ctypes.POINTER(ctypes.c_ubyte)()
    return int(lib.os_crc8(ptr, len(raw), int(poly) & 0xFFFF, int(init) & 0xFF)) & 0xFF


def crc16_ccitt(data, poly=CRC16_POLY, init=CRC16_INIT):
    lib = _lib()
    raw, arr = _as_u8_array(data)
    ptr = ctypes.cast(arr, ctypes.POINTER(ctypes.c_ubyte)) if raw else ctypes.POINTER(ctypes.c_ubyte)()
    return int(lib.os_crc16_ccitt(ptr, len(raw), int(poly) & 0xFFFF, int(init) & 0xFFFF)) & 0xFFFF


def derive_session_key(assigned_id, timestamp_raw):
    lib = _lib()
    aid = max(0, int(assigned_id or 0))
    ts = max(0, int(timestamp_raw or 0))
    out = (ctypes.c_ubyte * 32)()
    lib.os_derive_session_key(ctypes.c_ulonglong(aid), ctypes.c_ulonglong(ts), out)
    return bytes(out)


def xor_payload(payload, key, offset):
    if not payload:
        return b''
    if not key:
        return bytes(payload)
    lib = _lib()
    raw_payload, p_arr = _as_u8_array(payload)
    raw_key, k_arr = _as_u8_array(key)
    out = (ctypes.c_ubyte * len(raw_payload))()
    lib.os_xor_payload(
        ctypes.cast(p_arr, ctypes.POINTER(ctypes.c_ubyte)),
        len(raw_payload),
        ctypes.cast(k_arr, ctypes.POINTER(ctypes.c_ubyte)),
        len(raw_key),
        int(offset or 0),
        out,
    )
    return bytes(out)


def xor_payload_into(payload, key, offset, out_buffer):
    """Write XOR result into *out_buffer* and return written byte length."""
    if not payload:
        return 0
    if not key:
        out_view = memoryview(out_buffer).cast('B')
        src = bytes(payload)
        if len(out_view) < len(src):
            raise ValueError('output buffer is too small')
        out_view[:len(src)] = src
        return len(src)
    lib = _lib()
    raw_payload, p_arr = _as_u8_array(payload)
    raw_key, k_arr = _as_u8_array(key)
    out_view = memoryview(out_buffer).cast('B')
    p_len = len(raw_payload)
    if len(out_view) < p_len:
        raise ValueError('output buffer is too small')
    out_t = ctypes.c_ubyte * p_len
    out_arr = out_t.from_buffer(out_view)
    lib.os_xor_payload(
        ctypes.cast(p_arr, ctypes.POINTER(ctypes.c_ubyte)),
        p_len,
        ctypes.cast(k_arr, ctypes.POINTER(ctypes.c_ubyte)),
        len(raw_key),
        int(offset or 0),
        ctypes.cast(out_arr, ctypes.POINTER(ctypes.c_ubyte)),
    )
    return p_len

