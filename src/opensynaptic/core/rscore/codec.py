"""codec.py – Python ctypes wrapper for the RSCore native library.

Provides:
  RsBase62Codec      – drop-in for utils.base62.base62.Base62Codec
  cmd_is_data()      – wrapper around os_cmd_is_data
  cmd_normalize_data() – wrapper around os_cmd_normalize_data
  cmd_secure_variant() – wrapper around os_cmd_secure_variant
  has_rs_native()    – probe whether os_rscore shared library is present
  rs_version()       – return the embedded version string from the DLL
"""
import base64
import ctypes
import json
import struct
import threading
import time
import zlib
from pathlib import Path

_JSON_CTX_COUNTER = 0

from opensynaptic.utils import ctx, load_native_library, read_json

_LIB_NAME = 'os_rscore'
_lib_cache = None
_lib_configured = False
_has_header_parser = False
_has_crc_helpers = False
_has_auto_decompose = False
_has_solidity_compressor = False
_has_fusion_state = False
_has_pipeline_batch = False

ABI_CORE_SYMBOLS = (
    'os_b62_encode_i64',
    'os_b62_decode_i64',
    'os_cmd_is_data',
    'os_cmd_normalize_data',
    'os_cmd_secure_variant',
    'os_rscore_version',
)

ABI_CRC_SYMBOLS = (
    'os_crc8',
    'os_crc16_ccitt_pub',
)

ABI_HEADER_SYMBOLS = (
    'os_parse_header_min',
)

ABI_AUTO_DECOMPOSE_SYMBOLS = (
    'os_auto_decompose_input',
)

ABI_SOLIDITY_SYMBOLS = (
    'os_compressor_create_v1',
    'os_compressor_free_v1',
    'os_compress_fact_v1',
)

ABI_FUSION_STATE_SYMBOLS = (
    'os_fusion_state_create_v1',
    'os_fusion_state_free_v1',
    'os_fusion_state_seed_v1',
    'os_fusion_state_apply_v1',
    'os_fusion_state_receive_apply_v1',
)

ABI_FUSION_JSON_SYMBOLS = (
    'os_fusion_run_json_v1',
    'os_fusion_decompress_json_v1',
    'os_fusion_relay_json_v1',
)

ABI_NODE_JSON_SYMBOLS = (
    'os_node_ensure_id_json_v1',
    'os_node_transmit_json_v1',
    'os_node_dispatch_json_v1',
)

ABI_STANDARDIZE_JSON_SYMBOLS = (
    'os_standardize_json_v1',
)

ABI_HANDSHAKE_JSON_SYMBOLS = (
    'os_handshake_negotiate_v1',
)

ABI_TRANSPORT_JSON_SYMBOLS = (
    'os_transporter_send_v1',
    'os_transporter_listen_v1',
)

ABI_PIPELINE_BATCH_SYMBOLS = (
    'os_pipeline_batch_v1',
)


def _missing_symbols(required_symbols):
    lib = _lib()
    missing = []
    for symbol_name in required_symbols:
        if getattr(lib, symbol_name, None) is None:
            missing.append(symbol_name)
    return missing


def _require_symbols(required_symbols, feature_name):
    missing = _missing_symbols(required_symbols)
    if missing:
        raise RuntimeError(
            'os_rscore: {} ABI is unavailable, missing symbols={}'.format(feature_name, ','.join(missing))
        )


def rscore_abi_status() -> dict:
    """Return a Rust ABI capability matrix for diagnostics and CI visibility."""
    try:
        _lib()
    except Exception as e:
        return {
            'loaded': False,
            'error': str(e),
            'missing': {
                'core': list(ABI_CORE_SYMBOLS),
                'crc': list(ABI_CRC_SYMBOLS),
                'header': list(ABI_HEADER_SYMBOLS),
                'auto_decompose': list(ABI_AUTO_DECOMPOSE_SYMBOLS),
                'solidity': list(ABI_SOLIDITY_SYMBOLS),
                'fusion_state': list(ABI_FUSION_STATE_SYMBOLS),
                'fusion_json': list(ABI_FUSION_JSON_SYMBOLS),
                'node_json': list(ABI_NODE_JSON_SYMBOLS),
                'standardize_json': list(ABI_STANDARDIZE_JSON_SYMBOLS),
                'handshake_json': list(ABI_HANDSHAKE_JSON_SYMBOLS),
                'transport_json': list(ABI_TRANSPORT_JSON_SYMBOLS),
            },
        }

    return {
        'loaded': True,
        'missing': {
            'core': _missing_symbols(ABI_CORE_SYMBOLS),
            'crc': _missing_symbols(ABI_CRC_SYMBOLS),
            'header': _missing_symbols(ABI_HEADER_SYMBOLS),
            'auto_decompose': _missing_symbols(ABI_AUTO_DECOMPOSE_SYMBOLS),
            'solidity': _missing_symbols(ABI_SOLIDITY_SYMBOLS),
            'fusion_state': _missing_symbols(ABI_FUSION_STATE_SYMBOLS),
            'fusion_json': _missing_symbols(ABI_FUSION_JSON_SYMBOLS),
            'node_json': _missing_symbols(ABI_NODE_JSON_SYMBOLS),
            'standardize_json': _missing_symbols(ABI_STANDARDIZE_JSON_SYMBOLS),
            'handshake_json': _missing_symbols(ABI_HANDSHAKE_JSON_SYMBOLS),
            'transport_json': _missing_symbols(ABI_TRANSPORT_JSON_SYMBOLS),
        },
    }


def _lib():
    global _lib_cache, _lib_configured, _has_header_parser, _has_crc_helpers, _has_auto_decompose, _has_solidity_compressor, _has_fusion_state, _has_pipeline_batch
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
            # noinspection PyDeprecation
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
        # Optional batch pipeline ABI (os_pipeline_batch_v1)
        batch_fn = getattr(lib, 'os_pipeline_batch_v1', None)
        if batch_fn is not None:
            batch_fn.argtypes = [
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
            ]
            batch_fn.restype = ctypes.c_int
            _has_pipeline_batch = True
        else:
            _has_pipeline_batch = False
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


def has_pipeline_batch() -> bool:
    """Return True when the loaded RSCore DLL exports os_pipeline_batch_v1."""
    try:
        _lib()
    except Exception:
        return False
    return bool(_has_pipeline_batch)


class RsPipelineBatch:
    """Zero-overhead batch pipeline: compress + fuse N items in one Rust call.

    Eliminates per-item Python↔Rust round-trips.  Requires the DLL to export
    ``os_pipeline_batch_v1`` (check with :func:`has_pipeline_batch`).

    Binary input protocol (all multi-byte integers big-endian):
        u64 compressor_handle | u64 ctx_id | u32 item_count |
        u32 registry_root_len | bytes registry_root |
        repeat(item_count){ u32 aid | u8 strategy | u32 fact_len | bytes fact }

    Binary output protocol:
        u32 item_count | repeat{ u32 packet_len | bytes packet }

    Usage::

        batch = RsPipelineBatch(node.engine._rs_solidity, node.fusion._ffi)
        if batch.available:
            packed_facts = [RsPipelineBatch.pack_fact(f) for f in facts]
            packets = batch.run_batch([(pf, aid, True) for pf in packed_facts])
    """

    def __init__(self, compressor, fusion):
        self._compressor_handle = int(getattr(compressor, '_handle', 0) or 0)
        self._ctx_id = int(getattr(fusion, '_ctx_id', 0) or 0)
        self._registry_root = str(getattr(fusion, '_registry_root', '') or '')
        self._batch_proto_with_registry = True
        self._lib = _lib()
        self._fn = getattr(self._lib, 'os_pipeline_batch_v1', None)
        self.available = self._fn is not None and self._compressor_handle > 0
        # Pre-allocate reusable output buffer (128 KB; grows automatically)
        self._out_cap = 131072
        self._out_arr = (ctypes.c_ubyte * self._out_cap)()
        self._lock = threading.Lock()

    @staticmethod
    def pack_fact(fact: dict) -> bytes:
        """Serialize a fact dict to the binary format expected by os_compress_fact_v1.

        Equivalent to ``RsSolidityCompressor._pack_fact()`` but callable without
        a compressor instance – use for pre-computing items before a batch run.
        """
        blob = bytearray()

        def _pack_str(val: str) -> None:
            raw = str(val).encode('utf-8')
            blob.extend(struct.pack('>I', len(raw)))
            blob.extend(raw)

        _pack_str(fact.get('id', ''))
        _pack_str(fact.get('s', 'U'))
        blob.extend(struct.pack('>d', float(fact.get('t', 0))))

        sensors = []
        i = 1
        while True:
            sid = fact.get(f's{i}_id')
            if sid is None:
                break
            sensors.append((
                str(sid),
                str(fact.get(f's{i}_s', 'U')),
                float(fact.get(f's{i}_v', 0.0)),
                str(fact.get(f's{i}_u', '')),
            ))
            i += 1

        blob.extend(struct.pack('>I', len(sensors)))
        for sid, sst, val, unit in sensors:
            _pack_str(sid)
            _pack_str(sst)
            blob.extend(struct.pack('>d', val))
            _pack_str(unit)

        # Optional fields: geohash, url, msg → all absent (None sentinel = 0xFFFFFFFF)
        blob.extend(b'\xff\xff\xff\xff' * 3)
        return bytes(blob)

    def _invoke_batch(self, items: list, include_registry_root: bool) -> list:
        blob = bytearray()
        blob.extend(struct.pack('>QQ', self._compressor_handle, self._ctx_id))
        blob.extend(struct.pack('>I', len(items)))
        if include_registry_root:
            registry_root_raw = self._registry_root.encode('utf-8')
            blob.extend(struct.pack('>I', len(registry_root_raw)))
            blob.extend(registry_root_raw)
        for packed_fact, aid, strategy_full in items:
            blob.extend(struct.pack('>IBI', int(aid) & 0xFFFFFFFF, 1 if strategy_full else 0, len(packed_fact)))
            blob.extend(packed_fact)

        raw = bytes(blob)
        in_arr_t = ctypes.c_ubyte * len(raw)
        in_arr = in_arr_t.from_buffer_copy(raw)

        for _retry in range(2):
            written = int(self._fn(
                in_arr, ctypes.c_size_t(len(raw)),
                self._out_arr, ctypes.c_size_t(self._out_cap),
            ))
            if written == 0:
                return [b''] * len(items)
            if written < 0:
                new_cap = max(self._out_cap * 2, -written)
                self._out_cap = new_cap
                self._out_arr = (ctypes.c_ubyte * new_cap)()
                continue
            out_bytes = bytes(self._out_arr[:written])
            off = 0
            if len(out_bytes) < 4:
                return [b''] * len(items)
            count = struct.unpack_from('>I', out_bytes, off)[0]
            off += 4
            result = []
            for _ in range(count):
                if off + 4 > len(out_bytes):
                    result.append(b'')
                    continue
                plen = struct.unpack_from('>I', out_bytes, off)[0]
                off += 4
                if plen > 0 and off + plen <= len(out_bytes):
                    result.append(out_bytes[off:off + plen])
                    off += plen
                else:
                    result.append(b'')
            while len(result) < len(items):
                result.append(b'')
            return result
        return [b''] * len(items)

    def run_batch(self, items: list) -> list:
        """Call os_pipeline_batch_v1 for a list of (packed_fact, aid, strategy_full).

        Returns a list of ``bytes`` packets (b'' for any item that failed).
        Never raises; failed items produce empty bytes.
        """
        if not self.available or not items:
            return [b''] * len(items)

        # Shared buffer/cap state is process-wide in this object, so protect it.
        with self._lock:
            use_registry = bool(self._batch_proto_with_registry)
            result = self._invoke_batch(items, include_registry_root=use_registry)
            if use_registry and result and all((not p) for p in result):
                # Loaded DLL may still use legacy wire format (no registry_root field).
                legacy_result = self._invoke_batch(items, include_registry_root=False)
                if any(bool(p) for p in legacy_result):
                    self._batch_proto_with_registry = False
                    return legacy_result
            return result

        return [b''] * len(items)


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
    if not has_crc_helpers():
        raise RuntimeError('os_rscore: crc8 helper is unavailable')
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
    if not has_crc_helpers():
        raise RuntimeError('os_rscore: crc16 helper is unavailable')
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
        return _header_fallback(raw)

    out = (ctypes.c_ulonglong * 9)()
    arr_t = ctypes.c_ubyte * len(raw)
    arr = arr_t.from_buffer_copy(raw)
    ok = _lib().os_parse_header_min(arr, ctypes.c_size_t(len(raw)), out, ctypes.c_size_t(9))
    if int(ok) != 1:
        return _header_fallback(raw)
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


class RsOpenSynapticStandardizer:
    """Rust-only standardizer wrapper based on optional JSON ABI."""

    def __init__(self, *args, **kwargs):
        _require_symbols(ABI_STANDARDIZE_JSON_SYMBOLS, 'standardize_json')
        self._lib = _lib()
        self._fn = getattr(self._lib, 'os_standardize_json_v1', None)
        self._ctx = {'args': list(args), 'kwargs': dict(kwargs)}
        if self._fn is not None:
            self._fn.argtypes = [
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.c_size_t,
            ]
            self._fn.restype = ctypes.c_int

    def standardize(self, *args, **kwargs):
        if self._fn is None:
            raise RuntimeError('os_rscore: standardizer JSON ABI is unavailable')
        import json

        payload = json.dumps({'ctx': self._ctx, 'args': args, 'kwargs': kwargs}, ensure_ascii=True).encode('utf-8')
        in_arr_t = ctypes.c_ubyte * len(payload)
        in_arr = in_arr_t.from_buffer_copy(payload)
        cap = max(2048, len(payload) * 8 + 256)
        for _ in range(2):
            out_arr_t = ctypes.c_ubyte * cap
            out_arr = out_arr_t()
            written = int(self._fn(in_arr, ctypes.c_size_t(len(payload)), out_arr, ctypes.c_size_t(cap)))
            if written == 0:
                raise RuntimeError('os_rscore: standardize failed')
            if written < 0:
                cap = max(cap * 2, -written)
                continue
            out_raw = bytes(bytearray(out_arr)[:written])
            return json.loads(out_raw.decode('utf-8'))
        raise RuntimeError('os_rscore: standardize output exceeded retry budget')


class RsOSHandshakeManager:
    """Rust-only handshake wrapper with CMD helper bindings."""

    def __init__(self, *args, **kwargs):
        _require_symbols(ABI_CORE_SYMBOLS, 'core')
        self._lib = _lib()
        self._rs_cmd_is_data = cmd_is_data
        self._rs_cmd_normalize = cmd_normalize_data
        self._rs_cmd_secure = cmd_secure_variant
        self._negotiate_fn = getattr(self._lib, 'os_handshake_negotiate_v1', None)

    def negotiate(self, *args, **kwargs):
        if self._negotiate_fn is None:
            raise RuntimeError('os_rscore: handshake negotiate ABI is unavailable')
        raise RuntimeError('os_rscore: handshake negotiate ABI requires explicit Rust payload wiring')

    def is_secure_data_cmd(self, cmd):
        return int(cmd) != int(cmd_normalize_data(int(cmd) & 0xFF))

    def normalize_data_cmd(self, cmd):
        return int(cmd_normalize_data(int(cmd) & 0xFF))

    def secure_variant_cmd(self, cmd):
        return int(cmd_secure_variant(int(cmd) & 0xFF))


class RsTransporterManager:
    """Rust-only transporter wrapper based on optional send/listen ABI."""

    def __init__(self, *args, **kwargs):
        _require_symbols(ABI_TRANSPORT_JSON_SYMBOLS, 'transport_json')
        self._lib = _lib()
        self._ctx = {'args': list(args), 'kwargs': dict(kwargs)}
        self._send_fn = getattr(self._lib, 'os_transporter_send_v1', None)
        self._listen_fn = getattr(self._lib, 'os_transporter_listen_v1', None)

    def send(self, payload, config):
        if self._send_fn is None:
            raise RuntimeError('os_rscore: transporter send ABI is unavailable')
        raise RuntimeError('os_rscore: transporter send ABI requires explicit Rust payload wiring')

    def listen(self, config, callback):
        if self._listen_fn is None:
            raise RuntimeError('os_rscore: transporter listen ABI is unavailable')
        raise RuntimeError('os_rscore: transporter listen ABI requires explicit Rust callback wiring')


def _normalize_packet_bytes(packet) -> bytes:
    if isinstance(packet, bytes):
        return packet
    if isinstance(packet, memoryview):
        return packet.tobytes()
    if isinstance(packet, bytearray):
        return bytes(packet)
    if isinstance(packet, str):
        return packet.encode('utf-8', errors='ignore')
    return bytes(packet)


def _header_fallback(packet: bytes) -> dict:
    meta = {'crc16_ok': False, 'source_aid': 0}
    if len(packet) < 5:
        return meta
    try:
        recv = struct.unpack_from('>H', packet, len(packet) - 2)[0]
        calc = rs_crc16_ccitt(packet[:-2])
        meta['crc16_ok'] = (int(calc) == int(recv))
    except Exception:
        meta['crc16_ok'] = False
    try:
        r_cnt = int(packet[1])
        tid_pos = 2 + r_cnt * 4
        if r_cnt > 0 and tid_pos >= 6 and len(packet) > tid_pos:
            meta['source_aid'] = int.from_bytes(packet[tid_pos - 4:tid_pos], 'big')
    except Exception:
        pass
    return meta


class RsOSVisualFusionEngine:
    """Rust-only fusion wrapper."""

    def __init__(self, *args, **kwargs):
        global _JSON_CTX_COUNTER
        _require_symbols(ABI_FUSION_JSON_SYMBOLS, 'fusion_json')
        self._lib = _lib()
        self._rs_parse_header = parse_packet_header if has_header_parser() else None
        self._rs_auto_decompose = auto_decompose_input if has_auto_decompose() else None
        self._rs_crc8_fn = rs_crc8 if has_crc_helpers() else None
        self._rs_crc16_fn = rs_crc16_ccitt if has_crc_helpers() else None
        self._rs_fusion_state = RsFusionState() if has_fusion_state() else None
        self._rs_seeded_aids = set()
        self._rs_seeded_aids_limit = 10000
        # Keep context stable across repeated CLI commands in the same process so
        # Rust-side fusion templates survive node re-instantiation.
        self._ctx_id = int(self._derive_ctx_id(args, kwargs))
        self._registry_root = self._resolve_registry_root(args, kwargs)
        self.local_id = 0xFFFFFFFE
        self.local_id_str = str(self.local_id)
        self._single_route_ids = (self.local_id,)
        self._run_json_fn = getattr(self._lib, 'os_fusion_run_json_v1', None)
        self._dec_json_fn = getattr(self._lib, 'os_fusion_decompress_json_v1', None)
        self._relay_json_fn = getattr(self._lib, 'os_fusion_relay_json_v1', None)

        for fn in (self._run_json_fn, self._dec_json_fn, self._relay_json_fn):
            if fn is not None:
                fn.argtypes = [
                    ctypes.POINTER(ctypes.c_ubyte),
                    ctypes.c_size_t,
                    ctypes.POINTER(ctypes.c_ubyte),
                    ctypes.c_size_t,
                ]
                fn.restype = ctypes.c_int

    @staticmethod
    def _derive_ctx_id(args, kwargs) -> int:
        global _JSON_CTX_COUNTER
        cfg = args[0] if args else kwargs.get('config_path')
        if cfg is not None:
            seed = str(cfg)
            return int((zlib.crc32(seed.encode('utf-8')) & 0x7FFFFFFF) + 1)
        _JSON_CTX_COUNTER += 1
        return int(_JSON_CTX_COUNTER)

    @staticmethod
    def _resolve_registry_root(args, kwargs) -> str:
        cfg_path = args[0] if args else kwargs.get('config_path')
        cfg = {}
        if cfg_path:
            try:
                cfg = read_json(str(cfg_path)) or {}
            except Exception:
                cfg = {}
        elif isinstance(getattr(ctx, 'config', None), dict):
            cfg = dict(ctx.config)
        registry = ''
        try:
            registry = str((cfg.get('RESOURCES', {}) or {}).get('registry', '') or '')
        except Exception:
            registry = ''
        if registry:
            p = Path(registry)
            if not p.is_absolute():
                base = Path(cfg_path).resolve().parent if cfg_path else Path(str(getattr(ctx, 'root', '.')))
                p = base / p
        else:
            fallback = getattr(ctx, 'registry_dir', None)
            if fallback:
                p = Path(str(fallback))
            else:
                base = Path(cfg_path).resolve().parent if cfg_path else Path(str(getattr(ctx, 'root', '.')))
                p = base / 'data' / 'device_registry'
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return str(p)

    def _resolve_src_aid(self, raw_input) -> int:
        try:
            if isinstance(raw_input, (bytes, bytearray, memoryview)):
                s = bytes(raw_input).decode('utf-8', errors='ignore')
            else:
                s = str(raw_input)
            semi = s.find(';')
            if semi > 0:
                prefix = s[:semi].strip()
                if prefix.isdigit():
                    return int(prefix)
        except Exception:
            pass
        return 0

    def _route_ids_for(self, src_aid: int):
        return (int(src_aid),)

    def _seed_fusion_state_if_needed(self, src_aid: int):
        return None

    def _registry_path_for_aid(self, aid: int) -> Path:
        aid_str = str(int(aid)).zfill(10)
        return Path(self._registry_root) / aid_str[0:2] / aid_str[2:4] / '{}.json'.format(int(aid))

    def _load_registry_disk(self, aid: int) -> dict:
        p = self._registry_path_for_aid(aid)
        if p.exists():
            try:
                with p.open('r', encoding='utf-8') as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    templates = data.get('templates', {}) if isinstance(data.get('templates', {}), dict) else {}
                    return {'aid': str(int(aid)), 'templates': templates}
            except Exception:
                pass
        return {'aid': str(int(aid)), 'templates': {}}

    def _save_registry_disk(self, aid: int, data: dict):
        p = self._registry_path_for_aid(aid)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open('w', encoding='utf-8') as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception:
            return

    def _persist_full_payload(self, raw_input: str, source_aid: int, tid: int):
        decomp = auto_decompose_input(raw_input)
        if not decomp:
            return
        _ts, sig, vals = decomp
        sig_str = sig.decode('utf-8', errors='ignore') if isinstance(sig, (bytes, bytearray)) else str(sig)
        vals_b64 = [base64.b64encode(v).decode('ascii') for v in (vals or [])]
        data = self._load_registry_disk(int(source_aid))
        templates = data.setdefault('templates', {})
        templates[str(int(tid))] = {'sig': sig_str, 'last_vals_bin': vals_b64}
        self._save_registry_disk(int(source_aid), data)

    @staticmethod
    def _packet_tid_and_source(packet: bytes):
        if not packet or len(packet) < 10:
            return (None, None)
        try:
            route_count = int(packet[1])
            tid_pos = 2 + route_count * 4
            if len(packet) < tid_pos + 8:
                return (None, None)
            tid = int(packet[tid_pos])
            source_aid = 0
            if route_count > 0 and tid_pos >= 6:
                source_aid = int.from_bytes(packet[tid_pos - 4:tid_pos], 'big')
            return (tid, source_aid)
        except Exception:
            return (None, None)

    def run_engine(self, *args, **kwargs):
        if self._run_json_fn is None:
            raise RuntimeError('os_rscore: fusion run JSON ABI is unavailable')
        import json

        raw_input = args[0] if args else kwargs.get('raw_input', '')
        if isinstance(raw_input, memoryview):
            raw_input = raw_input.tobytes().decode('utf-8', errors='ignore')
        elif isinstance(raw_input, (bytes, bytearray)):
            raw_input = bytes(raw_input).decode('utf-8', errors='ignore')
        else:
            raw_input = str(raw_input)

        strategy = str(kwargs.get('strategy', 'DIFF')).upper()
        payload = json.dumps(
            {
                'ctx_id': int(self._ctx_id),
                'raw_input': raw_input,
                'strategy': strategy,
                'src_aid': int(self.local_id),
                'registry_root': str(self._registry_root),
            },
            ensure_ascii=True,
        ).encode('utf-8')
        packet = _run_json_abi(self._run_json_fn, payload)
        try:
            if packet:
                base_cmd = int(cmd_normalize_data(int(packet[0]) & 0xFF))
                if base_cmd == 63:
                    tid, src = self._packet_tid_and_source(packet)
                    src_aid = int(src if src not in (None, 0) else self._resolve_src_aid(raw_input) or self.local_id)
                    if tid is not None:
                        self._persist_full_payload(raw_input, src_aid, tid)
        except Exception:
            pass
        return packet

    def decompress(self, packet, *args, **kwargs):
        if self._dec_json_fn is None:
            raise RuntimeError('os_rscore: fusion decompress JSON ABI is unavailable')
        import json

        raw = _normalize_packet_bytes(packet)
        payload = json.dumps(
            {
                'ctx_id': int(self._ctx_id),
                'packet_b64': base64.b64encode(raw).decode('ascii'),
                'registry_root': str(self._registry_root),
            },
            ensure_ascii=True,
        ).encode('utf-8')
        out_raw = _run_json_abi(self._dec_json_fn, payload)
        decoded = json.loads(out_raw.decode('utf-8'))
        if isinstance(decoded, dict):
            meta = decoded.get('__packet_meta__', {}) if isinstance(decoded.get('__packet_meta__', {}), dict) else {}
            if int(meta.get('base_cmd', meta.get('cmd', 0)) or 0) == 63:
                try:
                    if len(self._rs_seeded_aids) >= self._rs_seeded_aids_limit:
                        self._rs_seeded_aids.clear()
                    self._rs_seeded_aids.add(int(meta.get('source_aid', 0)))
                except Exception:
                    pass
                # Symmetric bootstrap: FULL receive always refreshes on-disk template/runtime.
                try:
                    raw_packet = _normalize_packet_bytes(packet)
                    route_count = int(raw_packet[1]) if len(raw_packet) > 1 else 0
                    tid_pos = 2 + route_count * 4
                    if len(raw_packet) > (tid_pos + 7 + 3):
                        body = raw_packet[tid_pos + 7:-3]
                        body_str = body.decode('utf-8', errors='ignore')
                        tid = int(meta.get('tid', 0) or 0)
                        src_aid = int(meta.get('source_aid', 0) or 0)
                        if tid > 0 and body_str:
                            self._persist_full_payload(body_str, src_aid, tid)
                except Exception:
                    pass
        return decoded

    def relay(self, *args, **kwargs):
        if self._relay_json_fn is None:
            raise RuntimeError('os_rscore: fusion relay JSON ABI is unavailable')
        import json

        raw_input = args[0] if args else kwargs.get('raw_input', '')
        if isinstance(raw_input, memoryview):
            raw_input = raw_input.tobytes().decode('utf-8', errors='ignore')
        elif isinstance(raw_input, (bytes, bytearray)):
            raw_input = bytes(raw_input).decode('utf-8', errors='ignore')
        else:
            raw_input = str(raw_input)
        payload = json.dumps({'ctx_id': int(self._ctx_id), 'raw_input': raw_input, 'strategy': 'DIFF', 'registry_root': str(self._registry_root)}, ensure_ascii=True).encode('utf-8')
        return _run_json_abi(self._relay_json_fn, payload)

    def _set_local_id(self, local_id):
        self.local_id = int(local_id or 0)
        self.local_id_str = str(self.local_id)
        self._single_route_ids = (self.local_id,)

    def close(self):
        fusion = getattr(self, '_rs_fusion_state', None)
        if fusion is not None:
            try:
                fusion.close()
            except Exception:
                pass
            self._rs_fusion_state = None
        self._rs_seeded_aids.clear()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


class RsOpenSynaptic:
    """Rust-only node wrapper based on optional JSON ABI."""

    def __init__(self, *args, **kwargs):
        _require_symbols(ABI_NODE_JSON_SYMBOLS, 'node_json')
        self._lib = _lib()
        self._ctx = {'args': list(args), 'kwargs': dict(kwargs)}
        self._ensure_id_fn = getattr(self._lib, 'os_node_ensure_id_json_v1', None)
        self._transmit_fn = getattr(self._lib, 'os_node_transmit_json_v1', None)
        self._process_pipeline_fn = getattr(self._lib, 'os_node_process_pipeline_json_v1', None)
        self._process_pipeline_batch_fn = getattr(self._lib, 'os_node_process_pipeline_batch_json_v1', None)
        self._dispatch_fn = getattr(self._lib, 'os_node_dispatch_json_v1', None)

        for fn in (self._ensure_id_fn, self._transmit_fn, self._process_pipeline_fn, self._process_pipeline_batch_fn, self._dispatch_fn):
            if fn is not None:
                fn.argtypes = [
                    ctypes.POINTER(ctypes.c_ubyte),
                    ctypes.c_size_t,
                    ctypes.POINTER(ctypes.c_ubyte),
                    ctypes.c_size_t,
                ]
                fn.restype = ctypes.c_int

        # Rust component facades used as fallback when node_json ABI returns a stub payload.
        self.assigned_id = kwargs.get('assigned_id') if isinstance(kwargs, dict) else None
        self.device_id = kwargs.get('device_id') if isinstance(kwargs, dict) else None
        cfg = args[0] if args else kwargs.get('config_path')
        self._std = RsOpenSynapticStandardizer(cfg) if cfg is not None else RsOpenSynapticStandardizer()
        self._eng = None
        self._fus = None
        try:
            from opensynaptic.core.rscore.solidity import OpenSynapticEngine as _RsEngine
            from opensynaptic.core.rscore.unified_parser import OSVisualFusionEngine as _RsFusion

            self._eng = _RsEngine(cfg)
            self._fus = _RsFusion(cfg)
        except Exception:
            self._eng = None
            self._fus = None
        self._pipeline_batch = None
        self._last_batch_metrics = {
            'count': 0,
            'stage_timing_ms': {'standardize_ms': 0.0, 'compress_ms': 0.0, 'fuse_ms': 0.0},
            'source': 'none',
        }
        self._strategy_lock = threading.Lock()
        self._strategy_state = {}
        self._strategy_full_warmup = max(1, int(kwargs.get('target_sync_count', 3) or 3))

    @staticmethod
    def _strategy_from_packet(packet) -> str:
        """Infer strategy label from packet cmd for fallback paths."""
        if not packet:
            return 'FULL_PACKET'
        try:
            cmd = int(packet[0])
        except Exception:
            return 'FULL_PACKET'
        try:
            base_cmd = int(cmd_normalize_data(cmd & 0xFF))
        except Exception:
            base_cmd = int(cmd & 0xFF)
        if base_cmd == 170:
            return 'DIFF_PACKET'
        if base_cmd == 127:
            return 'HEART_PACKET'
        return 'FULL_PACKET'

    @staticmethod
    def _decode_packet_tuple(out):
        if isinstance(out, dict) and 'packet_b64' in out:
            packet = base64.b64decode(out.get('packet_b64', ''))
            aid = int(out.get('aid', 0))
            strategy = str(out.get('strategy') or RsOpenSynaptic._strategy_from_packet(packet))
            return (packet, aid, strategy)
        return None

    def _decode_batch_packet_tuples(self, out):
        if not isinstance(out, list):
            return None
        rows = []
        for item in out:
            decoded = self._decode_packet_tuple(item)
            if decoded is None:
                return None
            rows.append(decoded)
        return rows

    def _set_last_batch_metrics(self, count=0, standardize_ms=0.0, compress_ms=0.0, fuse_ms=0.0, source='none'):
        self._last_batch_metrics = {
            'count': int(count or 0),
            'stage_timing_ms': {
                'standardize_ms': float(standardize_ms or 0.0),
                'compress_ms': float(compress_ms or 0.0),
                'fuse_ms': float(fuse_ms or 0.0),
            },
            'source': str(source or 'none'),
        }

    def get_last_batch_metrics(self):
        return dict(self._last_batch_metrics)

    @staticmethod
    def _normalize_aid_value(aid):
        try:
            return int(aid)
        except Exception:
            return 0xFFFFFFFE

    def _decide_strategy_for_aid(self, aid) -> str:
        aid_key = str(self._normalize_aid_value(aid))
        with self._strategy_lock:
            self._strategy_state.setdefault(aid_key, {'count': 0, 'state': 'HANDSHAKING'})
        # DIFF mode still auto-emits FULL when template state is missing, but allows
        # immediate transition to DIFF/HEART once state exists.
        return 'DIFF'

    def _update_strategy_counters(self, aid, strategy_label):
        aid_key = str(self._normalize_aid_value(aid))
        now = int(time.time())
        with self._strategy_lock:
            entry = self._strategy_state.setdefault(aid_key, {'count': 0, 'state': 'HANDSHAKING'})
            entry['count'] = int(entry.get('count', 0)) + 1
            entry['last'] = now
            if str(strategy_label or '').upper() != 'FULL_PACKET' or int(entry['count']) >= int(self._strategy_full_warmup):
                entry['state'] = 'SYNCED'

    def _update_strategy_counters_from_packet(self, aid, packet):
        if not packet:
            return
        self._update_strategy_counters(aid, self._strategy_from_packet(packet))

    @staticmethod
    def _build_fact_from_sensors(device_id, device_status, sensors, **kwargs):
        fact = {'id': str(device_id or 'UNKNOWN'), 's': str(device_status or 'ONLINE'), 't': kwargs.get('t', 0)}
        idx = 1
        for row in (sensors or []):
            if not isinstance(row, (list, tuple)) or len(row) < 4:
                continue
            sid, sst, sval, sunit = row[0], row[1], row[2], row[3]
            fact[f's{idx}_id'] = str(sid)
            fact[f's{idx}_s'] = str(sst)
            fact[f's{idx}_v'] = float(sval)
            fact[f's{idx}_u'] = str(sunit)
            idx += 1
        return fact

    @staticmethod
    def _is_fact_valid(fact):
        return isinstance(fact, dict) and bool(fact.get('id')) and any(k.startswith('s1_') for k in fact.keys())

    def _standardize_or_build_fact(self, device_id, device_status, sensors, **kwargs):
        fact = None
        try:
            fact = self._std.standardize(device_id, device_status, sensors, **kwargs)
        except Exception:
            fact = None
        if self._is_fact_valid(fact):
            return fact
        return self._build_fact_from_sensors(device_id, device_status, sensors, **kwargs)

    def _fallback_pipeline(self, sensors=None, device_id=None, device_status='ONLINE', **kwargs):
        aid = kwargs.get('assigned_id', self.assigned_id)
        if aid in (None, '', 0, '0'):
            aid = 0xFFFFFFFE
        aid = self._normalize_aid_value(aid)
        target_id = device_id or self.device_id or 'UNKNOWN'
        target_status = device_status or 'ONLINE'

        if self._eng is None or self._fus is None:
            raise RuntimeError('os_rscore: process_pipeline fallback is unavailable')

        fact = self._build_fact_from_sensors(target_id, target_status, sensors, **kwargs)
        compressed = self._eng.compress(fact)
        set_local = getattr(self._fus, '_set_local_id', None)
        if callable(set_local):
            try:
                set_local(aid)
            except Exception:
                pass

        engine_strategy = self._decide_strategy_for_aid(aid)
        packet = self._fus.run_engine('{};{}'.format(aid, compressed), strategy=engine_strategy)
        self._update_strategy_counters_from_packet(aid, packet)
        return (packet, aid, self._strategy_from_packet(packet))

    @staticmethod
    def _normalize_batch_item(item, base_kwargs):
        if isinstance(item, dict):
            merged = dict(base_kwargs)
            merged.update(item)
        else:
            merged = dict(base_kwargs)
            merged['sensors'] = item
        return merged

    def _resolve_batcher(self):
        if self._pipeline_batch is not None and bool(getattr(self._pipeline_batch, 'available', False)):
            return self._pipeline_batch
        if self._eng is None or self._fus is None or (not has_pipeline_batch()):
            return None
        compressor = getattr(self._eng, '_rs_solidity', None)
        fusion_ffi = getattr(self._fus, '_ffi', None)
        if compressor is None or fusion_ffi is None:
            return None
        try:
            batcher = RsPipelineBatch(compressor, fusion_ffi)
        except Exception:
            return None
        if not bool(getattr(batcher, 'available', False)):
            return None
        self._pipeline_batch = batcher
        return self._pipeline_batch

    def ensure_id(self, *args, **kwargs):
        if self._ensure_id_fn is None:
            raise RuntimeError('os_rscore: node ensure_id JSON ABI is unavailable')
        import json

        payload = json.dumps({'ctx': self._ctx, 'args': args, 'kwargs': kwargs}, ensure_ascii=True).encode('utf-8')
        out_raw = _run_json_abi(self._ensure_id_fn, payload)
        return json.loads(out_raw.decode('utf-8'))

    def transmit(self, *args, **kwargs):
        if self._transmit_fn is None:
            raise RuntimeError('os_rscore: node transmit JSON ABI is unavailable')
        import json

        payload = json.dumps({'ctx': self._ctx, 'args': args, 'kwargs': kwargs}, ensure_ascii=True).encode('utf-8')
        out_raw = _run_json_abi(self._transmit_fn, payload)
        out = json.loads(out_raw.decode('utf-8'))
        decoded = self._decode_packet_tuple(out)
        if decoded is not None:
            self._update_strategy_counters_from_packet(decoded[1], decoded[0])
            return decoded

        # Fallback to component composition when node_json is present but not fully implemented.
        sensors = kwargs.get('sensors')
        if sensors is None and args:
            sensors = args[0]
        device_id = kwargs.get('device_id') or self.device_id or 'UNKNOWN'
        device_status = kwargs.get('device_status', 'ONLINE')
        aid = kwargs.get('assigned_id', self.assigned_id)
        if aid in (None, '', 0, '0'):
            aid = 0xFFFFFFFE

        fallback_kwargs = dict(kwargs)
        fallback_kwargs.pop('sensors', None)
        fallback_kwargs.pop('device_id', None)
        fallback_kwargs.pop('device_status', None)
        fallback_kwargs['assigned_id'] = aid
        return self._fallback_pipeline(sensors=sensors, device_id=device_id, device_status=device_status, **fallback_kwargs)

    def process_pipeline(self, *args, **kwargs):
        import json

        if self._process_pipeline_fn is not None:
            payload = json.dumps({'ctx': self._ctx, 'args': args, 'kwargs': kwargs}, ensure_ascii=True).encode('utf-8')
            out_raw = _run_json_abi(self._process_pipeline_fn, payload)
            out = json.loads(out_raw.decode('utf-8'))
            decoded = self._decode_packet_tuple(out)
            if decoded is not None:
                self._update_strategy_counters_from_packet(decoded[1], decoded[0])
                return decoded

        sensors = kwargs.get('sensors') if 'sensors' in kwargs else (args[0] if args else None)
        device_id = kwargs.get('device_id')
        device_status = kwargs.get('device_status', 'ONLINE')
        fallback_kwargs = dict(kwargs)
        fallback_kwargs.pop('sensors', None)
        fallback_kwargs.pop('device_id', None)
        fallback_kwargs.pop('device_status', None)
        return self._fallback_pipeline(sensors=sensors, device_id=device_id, device_status=device_status, **fallback_kwargs)

    def process_pipeline_batch(self, batch_items, **kwargs):
        import json

        items = list(batch_items or [])
        return_metrics = bool(kwargs.pop('return_metrics', True))
        if self._process_pipeline_batch_fn is not None:
            payload = json.dumps({'ctx': self._ctx, 'batch_items': items, 'kwargs': kwargs}, ensure_ascii=True).encode('utf-8')
            out_raw = _run_json_abi(self._process_pipeline_batch_fn, payload)
            out = json.loads(out_raw.decode('utf-8'))
            if isinstance(out, dict):
                decoded = self._decode_batch_packet_tuples(out.get('results'))
                if decoded is not None:
                    for packet, aid, _strategy in decoded:
                        self._update_strategy_counters_from_packet(aid, packet)
                    stage = out.get('stage_timing_ms') if isinstance(out.get('stage_timing_ms'), dict) else {}
                    self._set_last_batch_metrics(
                        count=len(decoded),
                        standardize_ms=stage.get('standardize_ms', 0.0),
                        compress_ms=stage.get('compress_ms', 0.0),
                        fuse_ms=stage.get('fuse_ms', 0.0),
                        source='process_pipeline_batch_abi',
                    )
                    return {
                        'results': decoded,
                        'stage_timing_ms': dict(self._last_batch_metrics.get('stage_timing_ms', {})),
                    } if return_metrics else decoded
            decoded = self._decode_batch_packet_tuples(out)
            if decoded is not None:
                for packet, aid, _strategy in decoded:
                    self._update_strategy_counters_from_packet(aid, packet)
                self._set_last_batch_metrics(count=len(decoded), source='process_pipeline_batch_abi_legacy')
                return {
                    'results': decoded,
                    'stage_timing_ms': dict(self._last_batch_metrics.get('stage_timing_ms', {})),
                } if return_metrics else decoded
        fallback_kwargs = dict(kwargs)
        fallback_kwargs['__skip_batch_abi'] = True
        fallback_results = self.transmit_batch(items, **fallback_kwargs)
        return {
            'results': fallback_results,
            'stage_timing_ms': dict(self._last_batch_metrics.get('stage_timing_ms', {})),
        } if return_metrics else fallback_results

    def transmit_fast(self, *args, **kwargs):
        return self.process_pipeline(*args, **kwargs)

    def transmit_batch(self, batch_items, **kwargs):
        items = list(batch_items or [])
        if not items:
            self._set_last_batch_metrics(count=0, source='empty')
            return []
        skip_batch_abi = bool(kwargs.pop('__skip_batch_abi', False))

        if (not skip_batch_abi) and self._process_pipeline_batch_fn is not None:
            try:
                out = self.process_pipeline_batch(items, return_metrics=False, **kwargs)
                if isinstance(out, dict):
                    maybe_rows = out.get('results')
                    if isinstance(maybe_rows, list):
                        return maybe_rows
                return out
            except Exception:
                pass

        normalized = [self._normalize_batch_item(item, kwargs) for item in items]
        if len(normalized) == 1:
            row = self.process_pipeline(**normalized[0])
            self._set_last_batch_metrics(count=1, source='single_item_fallback')
            return [row]
        results = [None] * len(normalized)

        batcher = self._resolve_batcher()
        if batcher is not None:
            t_std0 = time.perf_counter()
            packed_items = []
            packed_map = []
            for idx, item in enumerate(normalized):
                sensors = item.get('sensors')
                device_id = item.get('device_id') or self.device_id or 'UNKNOWN'
                device_status = item.get('device_status', 'ONLINE')
                aid = item.get('assigned_id', self.assigned_id)
                if aid in (None, '', 0, '0'):
                    aid = 0xFFFFFFFE
                aid = self._normalize_aid_value(aid)
                local_kwargs = {k: v for k, v in item.items() if k not in {'sensors', 'device_id', 'device_status'}}
                try:
                    fact = self._standardize_or_build_fact(device_id, device_status, sensors, **local_kwargs)
                    packed = RsPipelineBatch.pack_fact(fact)
                    strategy_full = self._decide_strategy_for_aid(aid) == 'FULL'
                    packed_items.append((packed, aid, strategy_full))
                    packed_map.append((idx, aid))
                except Exception:
                    continue

            if packed_items:
                t_std1 = time.perf_counter()
                t_run0 = t_std1
                packets = batcher.run_batch(packed_items)
                t_run1 = time.perf_counter()
                for (idx, aid), packet in zip(packed_map, packets):
                    if packet:
                        self._update_strategy_counters_from_packet(aid, packet)
                        results[idx] = (packet, aid, self._strategy_from_packet(packet))
                run_ms = (t_run1 - t_run0) * 1000.0
                self._set_last_batch_metrics(
                    count=len(packed_items),
                    standardize_ms=(t_std1 - t_std0) * 1000.0,
                    # Batch ABI currently reports fused run cost only; split equally for diagnostics.
                    compress_ms=run_ms / 2.0,
                    fuse_ms=run_ms / 2.0,
                    source='pipeline_batch_fallback',
                )
            else:
                self._set_last_batch_metrics(count=0, source='pipeline_batch_no_items')

        for idx, item in enumerate(normalized):
            if results[idx] is not None:
                continue
            results[idx] = self.process_pipeline(**item)
        if all(r is not None for r in results):
            if str(self._last_batch_metrics.get('source', 'none')) in {'none', 'empty', 'pipeline_batch_no_items'}:
                self._set_last_batch_metrics(count=len(results), source='process_pipeline_fallback')
            return results
        self._set_last_batch_metrics(count=len(results), source='process_pipeline_fallback')
        return results

    def dispatch(self, *args, **kwargs):
        if self._dispatch_fn is None:
            raise RuntimeError('os_rscore: node dispatch JSON ABI is unavailable')
        import json

        payload = json.dumps(
            {
                'ctx': _json_safe_abi_obj(self._ctx),
                'args': _json_safe_abi_obj(args),
                'kwargs': _json_safe_abi_obj(kwargs),
            },
            ensure_ascii=True,
        ).encode('utf-8')
        out_raw = _run_json_abi(self._dispatch_fn, payload)
        return json.loads(out_raw.decode('utf-8'))


def _run_json_abi(fn, payload: bytes) -> bytes:
    in_arr_t = ctypes.c_ubyte * len(payload)
    in_arr = in_arr_t.from_buffer_copy(payload)
    cap = max(2048, len(payload) * 8 + 256)
    for _ in range(2):
        out_arr_t = ctypes.c_ubyte * cap
        out_arr = out_arr_t()
        written = int(fn(in_arr, ctypes.c_size_t(len(payload)), out_arr, ctypes.c_size_t(cap)))
        if written == 0:
            raise RuntimeError('os_rscore: JSON ABI call failed')
        if written < 0:
            cap = max(cap * 2, -written)
            continue
        return bytes(bytearray(out_arr)[:written])
    raise RuntimeError('os_rscore: JSON ABI output exceeded retry budget')


def _json_safe_abi_obj(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return {
            '__type__': 'bytes_b64',
            'data': base64.b64encode(raw).decode('ascii'),
        }
    if isinstance(value, tuple):
        return [_json_safe_abi_obj(v) for v in value]
    if isinstance(value, list):
        return [_json_safe_abi_obj(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe_abi_obj(v) for k, v in value.items()}
    return value


