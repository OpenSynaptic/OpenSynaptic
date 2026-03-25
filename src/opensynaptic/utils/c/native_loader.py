import ctypes
import importlib
import os
import sys
from pathlib import Path
from opensynaptic.utils.errors import EnvironmentMissingError


_LIB_CACHE = {}
_BUILD_ATTEMPTED = False


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
    """Load os_rscore from an installed opensynaptic_rscore extension fallback.

    This supports environments where Rust is distributed as a Python extension
    wheel (maturin) rather than copied into utils/c/bin as os_rscore.*.
    """
    if str(base_name or '').strip().lower() != 'os_rscore':
        return None

    candidate_paths = []
    try:
        pkg = importlib.import_module('opensynaptic_rscore')
        pkg_file = getattr(pkg, '__file__', None)
        if pkg_file:
            p = Path(pkg_file)
            if p.suffix.lower() in {'.pyd', '.so', '.dylib', '.dll'}:
                candidate_paths.append(p)
    except Exception:
        pass

    for mod_name in ('opensynaptic_rscore._native', '_native'):
        try:
            mod = importlib.import_module(mod_name)
            mod_file = getattr(mod, '__file__', None)
            if mod_file:
                candidate_paths.append(Path(mod_file))
        except Exception:
            continue

    seen = set()
    for candidate in candidate_paths:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if not candidate.exists():
            continue
        try:
            return ctypes.CDLL(str(candidate))
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


