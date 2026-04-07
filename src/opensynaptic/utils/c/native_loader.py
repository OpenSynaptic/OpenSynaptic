import ctypes
import importlib
import os
import sys
import sysconfig
from pathlib import Path
from opensynaptic.utils.errors import EnvironmentMissingError


_LIB_CACHE = {}
_BUILD_ATTEMPTED = False
_NATIVE_DEBUG = os.getenv('OPENSYNAPTIC_NATIVE_DEBUG', '').strip().lower() in {'1', 'true', 'yes'}


def _dbg(msg):
    if _NATIVE_DEBUG:
        print(f'[native_loader] {msg}', file=sys.stderr, flush=True)


def _rs_extension_symbol_requirements(base_name):
    """Return required symbols for a native library base name.

    For ``os_security``, some symbols may have been inlined under thin LTO,
    but their ``_pub`` aliases survive.  The returned list uses the primary
    name; callers that need a resilient check should also consult
    ``_rs_extension_symbol_fallbacks``.
    """
    key = str(base_name or '').strip().lower()
    requirements = {
        'os_rscore': (),
        'os_base62': ('os_b62_encode_i64', 'os_b62_decode_i64'),
        'os_security': ('os_crc8',),
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
        _dbg(f'_try_load_rs({base_name}): no symbol requirements, returning None')
        return None

    _dbg(f'_try_load_rs({base_name}): required_symbols={required_symbols}')

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
        _dbg(f'  candidate added: {candidate} (exists={candidate.exists()})')

    try:
        from importlib import metadata as importlib_metadata
    except Exception:  # pragma: no cover - stdlib import should exist on supported Pythons
        importlib_metadata = None

    if importlib_metadata is not None:
        for dist_name in ('opensynaptic-rscore', 'opensynaptic_rscore', 'opensynaptic'):
            try:
                dist = importlib_metadata.distribution(dist_name)
            except Exception:
                _dbg(f'  dist({dist_name!r}): not found')
                continue
            for rel_path in list(getattr(dist, 'files', None) or []):
                name = Path(str(rel_path)).name.lower()
                if not (name.startswith('_native') or name.startswith('opensynaptic_rscore')):
                    continue
                if Path(name).suffix.lower() not in _shared_module_suffixes():
                    continue
                located = dist.locate_file(rel_path)
                _dbg(f'  dist({dist_name!r}) RECORD match: {rel_path} -> {located}')
                _add_candidate(located)

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
            _dbg(f'  skip non-existent candidate: {candidate}')
            continue
        # Try ctypes.PyDLL first (designed for Python C extensions), then fall
        # back to plain ctypes.CDLL.  On Linux the C-ABI bridge symbols
        # (os_b62_encode_i64, os_crc8, …) are present in .dynsym thanks to the
        # --export-dynamic-symbol flags emitted by build.rs; either loader
        # should find them via dlsym once the .so is opened.
        for _loader in (ctypes.PyDLL, ctypes.CDLL):
            try:
                lib = _loader(str(candidate))
                results = {s: hasattr(lib, s) for s in required_symbols}
                _dbg(f'  {_loader.__name__}({candidate.name}): {results}')
                if all(results.values()):
                    _dbg(f'  -> returning lib for {base_name}')
                    return lib
            except Exception as exc:
                _dbg(f'  {_loader.__name__}({candidate.name}): EXCEPTION {exc!r}')
                continue
    _dbg(f'_try_load_rs({base_name}): no candidate matched, returning None')
    return None


def load_native_library(base_name):
    key = str(base_name or '').strip().lower()
    if not key:
        return None
    if key in _LIB_CACHE:
        _dbg(f'load({key}): cache hit -> {_LIB_CACHE[key]}')
        return _LIB_CACHE[key]

    _dbg(f'load({key}): cache miss, searching...')
    ext = _shared_ext()
    filename = key + ext

    for candidate_dir in _native_dirs():
        candidate = candidate_dir / filename
        _dbg(f'load({key}): standalone check {candidate} exists={candidate.exists()}')
        if candidate.exists():
            try:
                lib = ctypes.CDLL(str(candidate))
                _LIB_CACHE[key] = lib
                _dbg(f'load({key}): standalone loaded OK')
                return lib
            except Exception as exc:
                _dbg(f'load({key}): standalone CDLL failed: {exc!r}')
                continue

    _dbg(f'load({key}): trying rscore extension (attempt 1)')
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

    _dbg(f'load({key}): trying rscore extension (attempt 2)')
    ext_lib = _try_load_rs_from_python_extension(base_name)
    if ext_lib is not None:
        _LIB_CACHE[key] = ext_lib
        return ext_lib

    _dbg(f'load({key}): all attempts failed, caching None')
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


