"""codec.py – Python ctypes wrapper for the RSCore native library.

Provides:
  RsBase62Codec      – drop-in for utils.base62.base62.Base62Codec
  cmd_is_data()      – wrapper around os_cmd_is_data
  cmd_normalize_data() – wrapper around os_cmd_normalize_data
  cmd_secure_variant() – wrapper around os_cmd_secure_variant
  has_rs_native()    – probe whether os_rscore shared library is present
  rs_version()       – return the embedded version string from the DLL
"""
import ctypes
import struct

from opensynaptic.utils.c.native_loader import load_native_library

_LIB_NAME = 'os_rscore'
_lib_cache = None
_lib_configured = False
_has_header_parser = False
_has_crc_helpers = False
_has_auto_decompose = False
_has_solidity_compressor = False
_has_fusion_state = False


def _lib():
    global _lib_cache, _lib_configured, _has_header_parser, _has_crc_helpers, _has_auto_decompose, _has_solidity_compressor, _has_fusion_state
    if _lib_cache is None:
        _lib_cache = load_native_library(_LIB_NAME)
    if _lib_cache is None:
        raise RuntimeError(
            'os_rscore native library not found. '
            'Build it with: python -u src/opensynaptic/core/rscore/build_rscore.py'
        )
    if not _lib_configured:
        lib = _lib_cache
        lib.os_b62_encode_i64.argtypes = [ctypes.c_longlong, ctypes.c_char_p, ctypes.c_size_t]
        lib.os_b62_encode_i64.restype = ctypes.c_int
        lib.os_b62_decode_i64.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
        lib.os_b62_decode_i64.restype = ctypes.c_longlong
        lib.os_cmd_is_data.argtypes = [ctypes.c_uint8]
        lib.os_cmd_is_data.restype = ctypes.c_int
        lib.os_cmd_normalize_data.argtypes = [ctypes.c_uint8]
        lib.os_cmd_normalize_data.restype = ctypes.c_uint8
        lib.os_cmd_secure_variant.argtypes = [ctypes.c_uint8]
        lib.os_cmd_secure_variant.restype = ctypes.c_uint8
        # Optional Stage-3 symbol: keep backward compatibility with older DLLs.
        parser_fn = getattr(lib, 'os_parse_header_min', None)
        if parser_fn is not None:
            parser_fn.argtypes = [
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_ulonglong),
                ctypes.c_size_t,
            ]
            parser_fn.restype = ctypes.c_int
            _has_header_parser = True
        else:
            _has_header_parser = False
        # Optional CRC helpers (os_crc8 + os_crc16_ccitt_pub).
        crc8_fn = getattr(lib, 'os_crc8', None)
        crc16_fn = getattr(lib, 'os_crc16_ccitt_pub', None)
        if crc8_fn is not None and crc16_fn is not None:
            crc8_fn.argtypes = [
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
                ctypes.c_ushort,
                ctypes.c_ubyte,
            ]
            crc8_fn.restype = ctypes.c_ubyte
            crc16_fn.argtypes = [
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
                ctypes.c_ushort,
                ctypes.c_ushort,
            ]
            crc16_fn.restype = ctypes.c_ushort
            _has_crc_helpers = True
        else:
            _has_crc_helpers = False
        decompose_fn = getattr(lib, 'os_auto_decompose_input', None)
        if decompose_fn is not None:
            decompose_fn.argtypes = [
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
            ]
            decompose_fn.restype = ctypes.c_int
            _has_auto_decompose = True
        else:
            _has_auto_decompose = False
        compressor_create = getattr(lib, 'os_compressor_create_v1', None)
        compressor_free = getattr(lib, 'os_compressor_free_v1', None)
        compressor_run = getattr(lib, 'os_compress_fact_v1', None)
        if compressor_create is not None and compressor_free is not None and compressor_run is not None:
            compressor_create.argtypes = [
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
            ]
            compressor_create.restype = ctypes.c_ulonglong
            compressor_free.argtypes = [ctypes.c_ulonglong]
            compressor_free.restype = ctypes.c_int
            compressor_run.argtypes = [
                ctypes.c_ulonglong,
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
            ]
            compressor_run.restype = ctypes.c_int
            _has_solidity_compressor = True
        else:
            _has_solidity_compressor = False
        fusion_create = getattr(lib, 'os_fusion_state_create_v1', None)
        fusion_free = getattr(lib, 'os_fusion_state_free_v1', None)
        fusion_seed = getattr(lib, 'os_fusion_state_seed_v1', None)
        fusion_apply = getattr(lib, 'os_fusion_state_apply_v1', None)
        fusion_recv = getattr(lib, 'os_fusion_state_receive_apply_v1', None)
        if fusion_create is not None and fusion_free is not None and fusion_seed is not None and fusion_apply is not None and fusion_recv is not None:
            fusion_create.argtypes = []
            fusion_create.restype = ctypes.c_ulonglong
            fusion_free.argtypes = [ctypes.c_ulonglong]
            fusion_free.restype = ctypes.c_int
            fusion_seed.argtypes = [
                ctypes.c_ulonglong,
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
            ]
            fusion_seed.restype = ctypes.c_int
            fusion_apply.argtypes = [
                ctypes.c_ulonglong,
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
            ]
            fusion_apply.restype = ctypes.c_int
            fusion_recv.argtypes = [
                ctypes.c_ulonglong,
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
            ]
            fusion_recv.restype = ctypes.c_int
            _has_fusion_state = True
        else:
            _has_fusion_state = False
        lib.os_rscore_version.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        lib.os_rscore_version.restype = ctypes.c_int
        _lib_configured = True
    return _lib_cache


def has_header_parser() -> bool:
    """Return True when the loaded RSCore DLL exports os_parse_header_min."""
    try:
        _lib()
    except Exception:
        return False
    return bool(_has_header_parser)


def has_crc_helpers() -> bool:
    """Return True when the loaded RSCore DLL exports os_crc8 + os_crc16_ccitt_pub."""
    try:
        _lib()
    except Exception:
        return False
    return bool(_has_crc_helpers)


def has_auto_decompose() -> bool:
    """Return True when the loaded RSCore DLL exports os_auto_decompose_input."""
    try:
        _lib()
    except Exception:
        return False
    return bool(_has_auto_decompose)


def has_solidity_compressor() -> bool:
    """Return True when the loaded RSCore DLL exports compressor create/run/free symbols."""
    try:
        _lib()
    except Exception:
        return False
    return bool(_has_solidity_compressor)


def has_fusion_state() -> bool:
    """Return True when the loaded RSCore DLL exports the fusion state handle ABI."""
    try:
        _lib()
    except Exception:
        return False
    return bool(_has_fusion_state)


def auto_decompose_input(raw_input) -> tuple[str, str, list[bytes]] | None:
    """Rust fast-path equivalent of pycore ``OSVisualFusionEngine._auto_decompose``.

    Returns ``(ts_str, full_sig, raw_vals)`` or ``None`` when the input is
    malformed or the symbol is unavailable.
    """
    if not has_auto_decompose():
        return None
    if raw_input is None:
        return None
    if isinstance(raw_input, str):
        raw = raw_input.encode('utf-8')
    elif isinstance(raw_input, memoryview):
        raw = raw_input.tobytes()
    elif isinstance(raw_input, (bytes, bytearray)):
        raw = bytes(raw_input)
    else:
        try:
            raw = bytes(raw_input)
        except Exception:
            raw = str(raw_input).encode('utf-8', errors='ignore')
    if not raw:
        return None

    lib = _lib()
    in_arr_t = ctypes.c_ubyte * len(raw)
    in_arr = in_arr_t.from_buffer_copy(raw)

    cap = max(1024, len(raw) * 8 + 256)
    for _ in range(2):
        out_arr_t = ctypes.c_ubyte * cap
        out_arr = out_arr_t()
        written = int(lib.os_auto_decompose_input(in_arr, ctypes.c_size_t(len(raw)), out_arr, ctypes.c_size_t(cap)))
        if written == 0:
            return None
        if written < 0:
            cap = max(cap * 2, -written)
            continue
        blob = bytes(bytearray(out_arr)[:written])
        try:
            off = 0
            ts_len, sig_len, val_count = struct.unpack_from('>III', blob, off)
            off += 12
            ts = blob[off:off + ts_len].decode('utf-8')
            off += ts_len
            full_sig = blob[off:off + sig_len].decode('utf-8')
            off += sig_len
            vals = []
            for _ in range(val_count):
                (v_len,) = struct.unpack_from('>I', blob, off)
                off += 4
                vals.append(blob[off:off + v_len])
                off += v_len
            if off != len(blob):
                return None
            return (ts, full_sig, vals)
        except Exception:
            return None
    return None


def rs_crc8(data, poly: int = 7, init: int = 0) -> int:
    """Compute CRC-8 over *data* using the Rust native implementation.

    Matches the C ``os_security`` ``crc8()`` output for the same parameters.
    Default: poly=7 (0x07), init=0.
    """
    lib = _lib()
    if isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
    elif isinstance(data, memoryview):
        raw = bytes(data)
    else:
        raw = bytes(data)
    n = len(raw)
    if n == 0:
        return int(init) & 0xFF
    arr_t = ctypes.c_ubyte * n
    arr = arr_t.from_buffer_copy(raw)
    return int(lib.os_crc8(arr, ctypes.c_size_t(n), ctypes.c_ushort(poly & 0xFFFF), ctypes.c_ubyte(init & 0xFF))) & 0xFF


def rs_crc16_ccitt(data, poly: int = 0x1021, init: int = 0xFFFF) -> int:
    """Compute CRC-16/CCITT over *data* using the Rust native implementation.

    Matches the C ``os_security`` ``crc16_ccitt()`` output for the same parameters.
    Default: poly=0x1021, init=0xFFFF.
    """
    lib = _lib()
    if isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
    elif isinstance(data, memoryview):
        raw = bytes(data)
    else:
        raw = bytes(data)
    n = len(raw)
    if n == 0:
        return int(init) & 0xFFFF
    arr_t = ctypes.c_ubyte * n
    arr = arr_t.from_buffer_copy(raw)
    return int(lib.os_crc16_ccitt_pub(arr, ctypes.c_size_t(n), ctypes.c_ushort(poly & 0xFFFF), ctypes.c_ushort(init & 0xFFFF))) & 0xFFFF


def has_rs_native() -> bool:
    """Return True when the os_rscore shared library can be loaded."""
    return load_native_library(_LIB_NAME) is not None


def rs_version() -> str:
    """Return the version string embedded in the RSCore DLL."""
    try:
        lib = _lib()
        buf = ctypes.create_string_buffer(128)
        ok = lib.os_rscore_version(buf, ctypes.sizeof(buf))
        if int(ok) == 1:
            return buf.value.decode('ascii', errors='replace')
    except Exception:
        pass
    return 'os_rscore/unavailable'


def cmd_is_data(cmd: int) -> bool:
    """Return True if *cmd* is a telemetry-data command byte."""
    return bool(_lib().os_cmd_is_data(ctypes.c_uint8(cmd & 0xFF)))


def cmd_normalize_data(cmd: int) -> int:
    """Return the base (non-secure) variant of *cmd*."""
    return int(_lib().os_cmd_normalize_data(ctypes.c_uint8(cmd & 0xFF)))


def cmd_secure_variant(cmd: int) -> int:
    """Return the secure variant of *cmd*."""
    return int(_lib().os_cmd_secure_variant(ctypes.c_uint8(cmd & 0xFF)))


def parse_packet_header(packet) -> dict | None:
    """Parse minimal packet header metadata using Rust fast-path.

    Returns None for malformed/short packets.
    """
    if packet is None:
        return None
    if isinstance(packet, memoryview):
        raw = packet.tobytes()
    elif isinstance(packet, bytearray):
        raw = bytes(packet)
    elif isinstance(packet, bytes):
        raw = packet
    else:
        try:
            raw = bytes(packet)
        except Exception:
            return None
    if len(raw) < 5:
        return None

    if not has_header_parser():
        return None

    out = (ctypes.c_ulonglong * 9)()
    arr_t = ctypes.c_ubyte * len(raw)
    arr = arr_t.from_buffer_copy(raw)
    ok = _lib().os_parse_header_min(arr, ctypes.c_size_t(len(raw)), out, ctypes.c_size_t(9))
    if int(ok) != 1:
        return None
    return {
        'cmd': int(out[0]),
        'base_cmd': int(out[1]),
        'secure': bool(out[2]),
        'route_count': int(out[3]),
        'tid_pos': int(out[4]),
        'source_aid': int(out[5]),
        'tid': int(out[6]),
        'timestamp_raw': int(out[7]),
        'crc16_ok': bool(out[8]),
    }


class RsBase62Codec:
    """Base62 codec backed by the Rust native library.

    Drop-in replacement for opensynaptic.utils.base62.base62.Base62Codec.
    Only instantiate when has_rs_native() is True.
    """

    def __init__(self, precision: int = 4):
        self._lib = _lib()
        self.precision_val = 10 ** precision

    def encode(self, n, use_precision: bool = True) -> str:
        try:
            val = int(round(float(n) * self.precision_val)) if use_precision else int(float(n))
        except Exception:
            return '0'
        out = ctypes.create_string_buffer(128)
        ok = self._lib.os_b62_encode_i64(ctypes.c_longlong(val), out, ctypes.sizeof(out))
        if int(ok) != 1:
            raise RuntimeError('os_rscore: base62 encode failed value={}'.format(n))
        return out.value.decode('ascii')

    def decode(self, s: str, use_precision: bool = True) -> float:
        if not s or s == '0':
            return 0.0
        ok = ctypes.c_int(0)
        raw = self._lib.os_b62_decode_i64(str(s).encode('ascii'), ctypes.byref(ok))
        if int(ok.value) != 1:
            raise RuntimeError('os_rscore: base62 decode failed s={!r}'.format(s))
        decoded_int = int(raw)
        if not use_precision:
            return float(decoded_int)
        return round(decoded_int / self.precision_val, 8)


class RsSolidityCompressor:
    """Rust-backed helper for ``pycore.solidity.OpenSynapticEngine.compress()``.

    This object owns a native compressor handle initialized with the engine's
    precision/use_ms settings and symbol maps.
    """

    def __init__(self, precision: int, use_ms: bool, units_map: dict, states_map: dict):
        if not has_solidity_compressor():
            raise RuntimeError('os_rscore: solidity compressor is unavailable')
        self._lib = _lib()
        self._handle = 0
        spec = bytearray()
        spec.extend(struct.pack('>I', int(precision)))
        spec.append(1 if bool(use_ms) else 0)

        units_items = sorted(
            ((str(k), str(v)) for k, v in (units_map or {}).items()),
            key=lambda kv: kv[0],
        )
        spec.extend(struct.pack('>I', len(units_items)))
        for k, v in units_items:
            kb = k.encode('utf-8')
            vb = v.encode('utf-8')
            spec.extend(struct.pack('>I', len(kb)))
            spec.extend(kb)
            spec.extend(struct.pack('>I', len(vb)))
            spec.extend(vb)

        states_items = sorted(
            ((str(k), str(v)) for k, v in (states_map or {}).items()),
            key=lambda kv: kv[0],
        )
        spec.extend(struct.pack('>I', len(states_items)))
        for k, v in states_items:
            kb = k.encode('utf-8')
            vb = v.encode('utf-8')
            spec.extend(struct.pack('>I', len(kb)))
            spec.extend(kb)
            spec.extend(struct.pack('>I', len(vb)))
            spec.extend(vb)

        arr_t = ctypes.c_ubyte * len(spec)
        arr = arr_t.from_buffer_copy(bytes(spec))
        handle = int(self._lib.os_compressor_create_v1(arr, ctypes.c_size_t(len(spec))))
        if handle <= 0:
            raise RuntimeError('os_rscore: failed to create solidity compressor')
        self._handle = handle

    def close(self):
        handle = int(getattr(self, '_handle', 0) or 0)
        if handle > 0:
            try:
                self._lib.os_compressor_free_v1(ctypes.c_ulonglong(handle))
            finally:
                self._handle = 0

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    @staticmethod
    def _pack_opt_str(blob: bytearray, value):
        if value is None:
            blob.extend((0xFF, 0xFF, 0xFF, 0xFF))
            return
        raw = str(value).encode('utf-8')
        blob.extend(struct.pack('>I', len(raw)))
        blob.extend(raw)

    def _pack_fact(self, data: dict) -> bytes:
        blob = bytearray()

        def _pack_str(val):
            raw = str(val).encode('utf-8')
            blob.extend(struct.pack('>I', len(raw)))
            blob.extend(raw)

        _pack_str(data.get('id', ''))
        _pack_str(data.get('s', 'U'))
        blob.extend(struct.pack('>d', float(data.get('t', 0))))

        sensors = []
        i = 1
        while True:
            p = f's{i}'
            sensor_id = data.get(f'{p}_id')
            if sensor_id is None:
                break
            sensors.append((
                str(sensor_id),
                str(data.get(f'{p}_s', 'U')),
                float(data.get(f'{p}_v', 0.0)),
                str(data.get(f'{p}_u', '')),
            ))
            i += 1
        blob.extend(struct.pack('>I', len(sensors)))
        for sid, sst, val, unit in sensors:
            _pack_str(sid)
            _pack_str(sst)
            blob.extend(struct.pack('>d', float(val)))
            _pack_str(unit)

        self._pack_opt_str(blob, data.get('geohash'))
        self._pack_opt_str(blob, data.get('url'))
        self._pack_opt_str(blob, data.get('msg'))
        return bytes(blob)

    def compress(self, data: dict) -> str:
        if not isinstance(data, dict):
            raise TypeError('RsSolidityCompressor.compress expects dict input')
        handle = int(getattr(self, '_handle', 0) or 0)
        if handle <= 0:
            raise RuntimeError('os_rscore: invalid compressor handle')
        packed = self._pack_fact(data)
        in_arr_t = ctypes.c_ubyte * len(packed)
        in_arr = in_arr_t.from_buffer_copy(packed)
        cap = max(1024, len(packed) * 8 + 256)
        for _ in range(2):
            out_arr_t = ctypes.c_ubyte * cap
            out_arr = out_arr_t()
            written = int(self._lib.os_compress_fact_v1(
                ctypes.c_ulonglong(handle),
                in_arr,
                ctypes.c_size_t(len(packed)),
                out_arr,
                ctypes.c_size_t(cap),
            ))
            if written == 0:
                raise RuntimeError('os_rscore: compress_fact failed')
            if written < 0:
                cap = max(cap * 2, -written)
                continue
            return bytes(bytearray(out_arr)[:written]).decode('utf-8')
        raise RuntimeError('os_rscore: compress_fact output exceeded retry budget')


class RsFusionState:
    """Rust-backed outbound fusion cache for `OSVisualFusionEngine.run_engine()`.

    Owns a native state handle that tracks per-AID template IDs and runtime
    values so Python can skip most dict/list-heavy outbound diff logic.
    """

    def __init__(self):
        if not has_fusion_state():
            raise RuntimeError('os_rscore: fusion state ABI is unavailable')
        self._lib = _lib()
        self._handle = int(self._lib.os_fusion_state_create_v1())
        if self._handle <= 0:
            raise RuntimeError('os_rscore: failed to create fusion state handle')

    def close(self):
        handle = int(getattr(self, '_handle', 0) or 0)
        if handle > 0:
            try:
                self._lib.os_fusion_state_free_v1(ctypes.c_ulonglong(handle))
            finally:
                self._handle = 0

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    @staticmethod
    def _pack_blob(blob: bytearray, value):
        raw = bytes(value)
        blob.extend(struct.pack('>I', len(raw)))
        blob.extend(raw)

    def seed_aid(self, src_aid: int, templates: dict, runtime_vals: dict):
        handle = int(getattr(self, '_handle', 0) or 0)
        if handle <= 0:
            raise RuntimeError('os_rscore: invalid fusion state handle')
        templates = templates or {}
        runtime_vals = runtime_vals or {}
        blob = bytearray()
        blob.extend(struct.pack('>I', int(src_aid) & 0xFFFFFFFF))
        tid_items = sorted(
            ((int(tid), tpl) for tid, tpl in templates.items() if str(tid).isdigit()),
            key=lambda kv: kv[0],
        )
        blob.extend(struct.pack('>I', len(tid_items)))
        for tid, tpl in tid_items:
            sig = tpl.get('sig', '') if isinstance(tpl, dict) else ''
            sig_b = str(sig).encode('utf-8')
            vals = runtime_vals.get(str(tid), runtime_vals.get(tid, [])) or []
            blob.extend(struct.pack('>I', tid))
            self._pack_blob(blob, sig_b)
            blob.extend(struct.pack('>I', len(vals)))
            for v in vals:
                self._pack_blob(blob, bytes(v))
        raw = bytes(blob)
        arr_t = ctypes.c_ubyte * len(raw)
        arr = arr_t.from_buffer_copy(raw)
        ok = int(self._lib.os_fusion_state_seed_v1(
            ctypes.c_ulonglong(handle),
            arr,
            ctypes.c_size_t(len(raw)),
        ))
        if ok != 1:
            raise RuntimeError('os_rscore: fusion state seed failed aid={}'.format(src_aid))

    def apply(self, src_aid: int, strategy: str, sig: str, vals_bin: list[bytes]) -> dict:
        handle = int(getattr(self, '_handle', 0) or 0)
        if handle <= 0:
            raise RuntimeError('os_rscore: invalid fusion state handle')
        blob = bytearray()
        blob.extend(struct.pack('>I', int(src_aid) & 0xFFFFFFFF))
        blob.append(1 if str(strategy).upper() == 'FULL' else 0)
        sig_b = str(sig).encode('utf-8')
        self._pack_blob(blob, sig_b)
        vals = [bytes(v) for v in (vals_bin or [])]
        blob.extend(struct.pack('>I', len(vals)))
        for v in vals:
            self._pack_blob(blob, v)
        raw = bytes(blob)
        in_arr_t = ctypes.c_ubyte * len(raw)
        in_arr = in_arr_t.from_buffer_copy(raw)
        cap = max(256, len(raw) * 4 + 64)
        for _ in range(2):
            out_arr_t = ctypes.c_ubyte * cap
            out_arr = out_arr_t()
            written = int(self._lib.os_fusion_state_apply_v1(
                ctypes.c_ulonglong(handle),
                in_arr,
                ctypes.c_size_t(len(raw)),
                out_arr,
                ctypes.c_size_t(cap),
            ))
            if written == 0:
                raise RuntimeError('os_rscore: fusion state apply failed aid={}'.format(src_aid))
            if written < 0:
                cap = max(cap * 2, -written)
                continue
            blob_out = bytes(bytearray(out_arr)[:written])
            off = 0
            cmd = blob_out[off]
            off += 1
            (tid_num,) = struct.unpack_from('>I', blob_out, off)
            off += 4
            flags = blob_out[off]
            off += 1
            (body_len,) = struct.unpack_from('>I', blob_out, off)
            off += 4
            body = blob_out[off:off + body_len]
            return {
                'cmd': int(cmd),
                'tid': str(int(tid_num)).zfill(2),
                'new_template': bool(flags & 0x01),
                'runtime_changed': bool(flags & 0x02),
                'use_raw_input_body': bool(flags & 0x04),
                'body': body,
            }
        raise RuntimeError('os_rscore: fusion state apply output exceeded retry budget')

    def receive_apply(self, src_aid: int, base_cmd: int, tid: str | int, ts_enc: str, body) -> bytes:
        handle = int(getattr(self, '_handle', 0) or 0)
        if handle <= 0:
            raise RuntimeError('os_rscore: invalid fusion state handle')
        blob = bytearray()
        blob.extend(struct.pack('>I', int(src_aid) & 0xFFFFFFFF))
        blob.append(int(base_cmd) & 0xFF)
        blob.extend(struct.pack('>I', int(tid)))
        ts_b = str(ts_enc).encode('utf-8')
        self._pack_blob(blob, ts_b)
        self._pack_blob(blob, bytes(body))
        raw = bytes(blob)
        in_arr_t = ctypes.c_ubyte * len(raw)
        in_arr = in_arr_t.from_buffer_copy(raw)
        cap = max(512, len(raw) * 8 + 256)
        for _ in range(2):
            out_arr_t = ctypes.c_ubyte * cap
            out_arr = out_arr_t()
            written = int(self._lib.os_fusion_state_receive_apply_v1(
                ctypes.c_ulonglong(handle),
                in_arr,
                ctypes.c_size_t(len(raw)),
                out_arr,
                ctypes.c_size_t(cap),
            ))
            if written == 0:
                raise RuntimeError('os_rscore: fusion state receive_apply failed aid={} tid={}'.format(src_aid, tid))
            if written < 0:
                cap = max(cap * 2, -written)
                continue
            return bytes(bytearray(out_arr)[:written])
        raise RuntimeError('os_rscore: fusion state receive_apply output exceeded retry budget')


