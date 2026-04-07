import ctypes
import hashlib
import importlib
import os
import sys
import sysconfig
from pathlib import Path
from opensynaptic.utils.errors import EnvironmentMissingError


_LIB_CACHE = {}
_BUILD_ATTEMPTED = False
_B62_CHARS = b'0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
_B62_DECODE = {ch: idx for idx, ch in enumerate(_B62_CHARS)}


def _rs_extension_symbol_requirements(base_name):
    key = str(base_name or '').strip().lower()
    requirements = {
        'os_rscore': (),
        'os_base62': ('os_b62_encode_i64', 'os_b62_decode_i64'),
        'os_security': ('os_crc8', 'os_crc16_ccitt', 'os_xor_payload', 'os_derive_session_key'),
    }
    return requirements.get(key)


class NativeLibraryUnavailable(EnvironmentMissingError):
    def __init__(self, base_name, ext, message):
        install_urls = [
            'https://visualstudio.microsoft.com/visual-cpp-build-tools/',
            'https://www.msys2.org/',
            'https://clang.llvm.org/get_started.html',
        ]
        install_commands = [
            'python -u src/opensynaptic/utils/c/check_native_toolchain.py',
            'python -u src/opensynaptic/utils/c/build_native.py',
        ]
        super().__init__(
            message=message,
            missing_kind='native_library',
            resource='{}{}'.format(base_name, ext),
            install_urls=install_urls,
            install_commands=install_commands,
            details={'library': base_name, 'extension': ext},
        )


def _shared_ext():
    if os.name == 'nt':
        return '.dll'
    if sys.platform.startswith('darwin'):
        return '.dylib'
    return '.so'


def _shared_module_suffixes():
    return {'.pyd', '.so', '.dylib', '.dll'}


class _ShimFunction:
    def __init__(self, func):
        self._func = func
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        return self._func(*args)


class _ShimLibrary:
    def __init__(self, symbols):
        for name, func in symbols.items():
            setattr(self, name, _ShimFunction(func))


def _coerce_int(value, default=0):
    if hasattr(value, 'value'):
        value = value.value
    if value is None:
        return default
    try:
        return int(value)
    except Exception:
        return default


def _buffer_address(value):
    if value is None:
        return 0
    try:
        return ctypes.addressof(value)
    except Exception:
        pass
    try:
        return int(ctypes.cast(value, ctypes.c_void_p).value or 0)
    except Exception:
        return 0


def _read_raw_bytes(value, length):
    size = max(0, _coerce_int(length))
    if size == 0:
        return b''
    if isinstance(value, str):
        return value.encode('utf-8')[:size]
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)[:size]
    try:
        view = memoryview(value).cast('B')
        return bytes(view[:size])
    except Exception:
        pass
    addr = _buffer_address(value)
    if not addr:
        return b''
    return ctypes.string_at(addr, size)


def _read_c_string(value):
    if isinstance(value, str):
        return value.encode('ascii', 'strict')
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).split(b'\0', 1)[0]
    try:
        view = memoryview(value).cast('B')
        raw = bytes(view)
        return raw.split(b'\0', 1)[0]
    except Exception:
        pass
    try:
        raw = ctypes.cast(value, ctypes.c_char_p).value
    except Exception:
        raw = None
    return raw or b''


def _write_bytes(target, data):
    addr = _buffer_address(target)
    if not addr:
        return False
    payload = bytes(data)
    if payload:
        ctypes.memmove(addr, payload, len(payload))
    return True


def _write_c_int(target, value):
    addr = _buffer_address(target)
    if not addr:
        return False
    ctypes.cast(addr, ctypes.POINTER(ctypes.c_int))[0] = _coerce_int(value)
    return True


def _crc8_bytes(data, poly, init):
    crc = init & 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def _crc16_ccitt_bytes(data, poly, init):
    crc = init & 0xFFFF
    for byte in data:
        crc ^= (byte << 8) & 0xFFFF
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def _shim_b62_encode_i64(value, out, out_len):
    value = _coerce_int(value)
    out_len = max(0, _coerce_int(out_len))
    if not _buffer_address(out) or out_len < 2:
        return 0
    if value == 0:
        encoded = b'0\0'
        return 1 if len(encoded) <= out_len and _write_bytes(out, encoded) else 0

    negative = value < 0
    n = abs(value)
    encoded_bytes = bytearray()
    while n > 0:
        encoded_bytes.append(_B62_CHARS[n % 62])
        n //= 62
    encoded = (b'-' if negative else b'') + bytes(reversed(encoded_bytes)) + b'\0'
    if len(encoded) > out_len:
        return 0
    return 1 if _write_bytes(out, encoded) else 0


def _shim_b62_decode_i64(s, ok):
    _write_c_int(ok, 0)
    raw = _read_c_string(s)
    if not raw:
        return 0
    negative = False
    if raw.startswith(b'-'):
        negative = True
        raw = raw[1:]
        if not raw:
            return 0
    value = 0
    for byte in raw:
        digit = _B62_DECODE.get(byte)
        if digit is None:
            return 0
        value = (value * 62) + digit
    _write_c_int(ok, 1)
    return -value if negative else value


def _shim_crc8(data, length, poly, init):
    raw = _read_raw_bytes(data, length)
    return _crc8_bytes(raw, _coerce_int(poly) & 0xFFFF, _coerce_int(init) & 0xFF)


def _shim_crc16_ccitt(data, length, poly, init):
    raw = _read_raw_bytes(data, length)
    return _crc16_ccitt_bytes(raw, _coerce_int(poly) & 0xFFFF, _coerce_int(init) & 0xFFFF)


def _shim_xor_payload(payload, payload_len, key, key_len, offset, out):
    out_addr = _buffer_address(out)
    if not out_addr:
        return None
    raw_payload = _read_raw_bytes(payload, payload_len)
    if not raw_payload:
        return None
    raw_key = _read_raw_bytes(key, key_len)
    off = _coerce_int(offset) & 31
    if not raw_key:
        result = raw_payload
    else:
        key_len = len(raw_key)
        result = bytes(
            (byte ^ raw_key[(idx + off) % key_len] ^ off) & 0xFF
            for idx, byte in enumerate(raw_payload)
        )
    _write_bytes(out, result)
    return None


def _shim_derive_session_key(assigned_id, timestamp_raw, out32):
    if not _buffer_address(out32):
        return None
    mask = (1 << 64) - 1
    seed = (_coerce_int(assigned_id) & mask) * (_coerce_int(timestamp_raw) & mask)
    seed &= mask
    digest = hashlib.sha256(str(seed).encode('ascii')).digest()
    _write_bytes(out32, digest)
    return None


def _try_python_abi_shim(base_name, candidate_paths):
    if not candidate_paths:
        return None
    try:
        pkg = importlib.import_module('opensynaptic_rscore')
        abi_info = getattr(pkg, 'abi_info_py', None)
        if not callable(abi_info):
            return None
        abi_info()
    except Exception:
        return None

    key = str(base_name or '').strip().lower()
    if key == 'os_base62':
        return _ShimLibrary({
            'os_b62_encode_i64': _shim_b62_encode_i64,
            'os_b62_decode_i64': _shim_b62_decode_i64,
        })
    if key == 'os_security':
        return _ShimLibrary({
            'os_crc8': _shim_crc8,
            'os_crc16_ccitt': _shim_crc16_ccitt,
            'os_xor_payload': _shim_xor_payload,
            'os_derive_session_key': _shim_derive_session_key,
        })
    return None


def _iter_shared_modules(root: Path):
    try:
        if not root.exists():
            return
    except Exception:
        return
    patterns = (
        'opensynaptic_rscore*',
        'opensynaptic_rscore/**/*',
        'opensynaptic_rscore/**/*.pyd',
        'opensynaptic_rscore/**/*.so',
        'opensynaptic_rscore/**/*.dylib',
        'opensynaptic_rscore/**/*.dll',
    )
    seen = set()
    for pattern in patterns:
        try:
            matches = root.glob(pattern)
        except Exception:
            continue
        for candidate in matches:
            try:
                resolved = candidate.resolve()
            except Exception:
                resolved = candidate
            key = str(resolved)
            if key in seen or not candidate.is_file():
                continue
            seen.add(key)
            if candidate.suffix.lower() in _shared_module_suffixes():
                yield candidate


def _native_dirs():
    env = os.getenv('OPENSYNAPTIC_NATIVE_DIR', '').strip()
    dirs = []
    if env:
        dirs.append(Path(env))
    root = Path(__file__).resolve().parent
    dirs.append(root / 'bin')
    dirs.append(root)
    return dirs


def _try_build_once():
    global _BUILD_ATTEMPTED
    if _BUILD_ATTEMPTED:
        return
    _BUILD_ATTEMPTED = True
    if os.getenv('OPENSYNAPTIC_AUTO_BUILD_NATIVE', '0').strip().lower() in {'0', 'false', 'no'}:
        return
    try:
        from opensynaptic.utils.c.build_native import build_all
        build_all()
    except Exception:
        return


def _try_load_rs_from_python_extension(base_name):
    """Load ABI-compatible symbols from the installed opensynaptic_rscore extension.

    This supports wheel layouts where the Rust extension is shipped as the
    runtime carrier for os_rscore and compatible os_base62 / os_security C ABI
    symbols instead of separate utils/c/bin shared libraries.
    """
    required_symbols = _rs_extension_symbol_requirements(base_name)
    if required_symbols is None:
        return None

    candidate_paths = []
    seen_paths = set()

    def _add_candidate(path_value):
        if not path_value:
            return
        try:
            candidate = Path(path_value)
        except Exception:
            return
        if candidate.suffix.lower() not in _shared_module_suffixes():
            return
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen_paths:
            return
        seen_paths.add(key)
        candidate_paths.append(candidate)

    try:
        from importlib import metadata as importlib_metadata
    except Exception:  # pragma: no cover - stdlib import should exist on supported Pythons
        importlib_metadata = None

    if importlib_metadata is not None:
        # Search both the standalone rscore distribution (if packaged separately)
        # and the parent 'opensynaptic' distribution (when rscore is bundled in
        # the same wheel, as is the case for binary wheels built with maturin).
        for dist_name in ('opensynaptic-rscore', 'opensynaptic_rscore', 'opensynaptic'):
            try:
                dist = importlib_metadata.distribution(dist_name)
            except Exception:
                continue
            for rel_path in list(getattr(dist, 'files', None) or []):
                name = Path(str(rel_path)).name.lower()
                if not (name.startswith('_native') or name.startswith('opensynaptic_rscore')):
                    continue
                if Path(name).suffix.lower() not in _shared_module_suffixes():
                    continue
                _add_candidate(dist.locate_file(rel_path))

    site_roots = []
    for key in ('platlib', 'purelib'):
        try:
            root = sysconfig.get_paths().get(key)
        except Exception:
            root = None
        if root:
            site_roots.append(Path(root))
    try:
        import site as _site
        site_roots.extend(Path(p) for p in _site.getsitepackages())
    except Exception:
        pass

    seen_roots = set()
    for root in site_roots:
        root_key = str(root)
        if root_key in seen_roots or not root.exists():
            continue
        seen_roots.add(root_key)
        for candidate in _iter_shared_modules(root):
            _add_candidate(candidate)

    try:
        pkg = importlib.import_module('opensynaptic_rscore')
        pkg_file = getattr(pkg, '__file__', None)
        if pkg_file:
            p = Path(pkg_file)
            if p.suffix.lower() in {'.pyd', '.so', '.dylib', '.dll'}:
                _add_candidate(p)
        for pkg_root in list(getattr(pkg, '__path__', []) or []):
            for candidate in _iter_shared_modules(Path(pkg_root).parent):
                _add_candidate(candidate)
    except Exception:
        pass

    for mod_name in ('opensynaptic_rscore.opensynaptic_rscore', 'opensynaptic_rscore._native', '_native'):
        try:
            mod = importlib.import_module(mod_name)
            mod_file = getattr(mod, '__file__', None)
            if mod_file:
                _add_candidate(mod_file)
        except Exception:
            continue

    for candidate in candidate_paths:
        if not candidate.exists():
            continue
        # Try ctypes.PyDLL first (designed for Python C extensions), then fall
        # back to plain ctypes.CDLL.  On Linux the C-ABI bridge symbols
        # (os_b62_encode_i64, os_crc8, …) are present in .dynsym thanks to the
        # companion linker version script emitted by build.rs; either loader
        # should find them via dlsym once the .so is opened.
        for _loader in (ctypes.PyDLL, ctypes.CDLL):
            try:
                lib = _loader(str(candidate))
                if all(hasattr(lib, symbol) for symbol in required_symbols):
                    return lib
            except Exception:
                continue
    shim = _try_python_abi_shim(base_name, candidate_paths)
    if shim is not None:
        return shim
    return None


def load_native_library(base_name):
    key = str(base_name or '').strip().lower()
    if not key:
        return None
    if key in _LIB_CACHE:
        return _LIB_CACHE[key]

    ext = _shared_ext()
    filename = key + ext

    for candidate_dir in _native_dirs():
        candidate = candidate_dir / filename
        if candidate.exists():
            try:
                lib = ctypes.CDLL(str(candidate))
                _LIB_CACHE[key] = lib
                return lib
            except Exception:
                continue

    ext_lib = _try_load_rs_from_python_extension(base_name)
    if ext_lib is not None:
        _LIB_CACHE[key] = ext_lib
        return ext_lib

    _try_build_once()

    for candidate_dir in _native_dirs():
        candidate = candidate_dir / filename
        if candidate.exists():
            try:
                lib = ctypes.CDLL(str(candidate))
                _LIB_CACHE[key] = lib
                return lib
            except Exception:
                continue

    ext_lib = _try_load_rs_from_python_extension(base_name)
    if ext_lib is not None:
        _LIB_CACHE[key] = ext_lib
        return ext_lib

    _LIB_CACHE[key] = None
    return None


def has_native_library(base_name):
    return load_native_library(base_name) is not None


def require_native_library(base_name):
    lib = load_native_library(base_name)
    if lib is not None:
        return lib
    ext = _shared_ext()
    msg = (
        'Missing native library [{}{}]. Build it with "python -u src/opensynaptic/utils/c/build_native.py" '
        'or place it under OPENSYNAPTIC_NATIVE_DIR / src/opensynaptic/utils/c/bin/'.format(base_name, ext)
    )
    raise NativeLibraryUnavailable(base_name, ext, msg)


