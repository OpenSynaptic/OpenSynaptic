import ctypes
import importlib
import os
import sys
import sysconfig
from pathlib import Path
from opensynaptic.utils.errors import EnvironmentMissingError


_LIB_CACHE = {}
_BUILD_ATTEMPTED = False


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

    for mod_name in ('opensynaptic_rscore._native', '_native'):
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
        try:
            lib = ctypes.CDLL(str(candidate))
            if all(hasattr(lib, symbol) for symbol in required_symbols):
                return lib
        except Exception:
            continue
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


