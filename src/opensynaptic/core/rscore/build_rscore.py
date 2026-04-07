"""build_rscore.py – Compile the RSCore Rust crate and install the shared
library into the native-loader search path.

Usage (standalone):
    python -u src/opensynaptic/core/rscore/build_rscore.py

Usage (from Python):
    from opensynaptic.core.rscore.build_rscore import build_rscore
    result = build_rscore(show_progress=True)
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CRATE_DIR = _HERE / 'rust'

# Destination: same bin/ directory that build_native.py writes into.
# Path: src/opensynaptic/utils/c/bin/
_NATIVE_BIN = _HERE.parents[1] / 'utils' / 'c' / 'bin'

_LIB_NAME = 'os_rscore'


def _shared_ext():
    if os.name == 'nt':
        return '.dll'
    if sys.platform.startswith('darwin'):
        return '.dylib'
    return '.so'


def _cargo_lib_filename():
    """Return the filename Cargo produces in target/release/ for this platform."""
    base = 'opensynaptic_rscore'
    if os.name == 'nt':
        return base + '.dll'
    if sys.platform.startswith('darwin'):
        return 'lib' + base + '.dylib'
    return 'lib' + base + '.so'


def _find_cargo():
    exe = shutil.which('cargo')
    if exe:
        return exe
    # Common Rust install locations
    home = Path.home()
    candidates = [
        home / '.cargo' / 'bin' / 'cargo',
        home / '.cargo' / 'bin' / 'cargo.exe',
        Path(r'C:\Users') / os.environ.get('USERNAME', '') / '.cargo' / 'bin' / 'cargo.exe',
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _cargo_target_root():
    """Return Cargo target root, honoring CARGO_TARGET_DIR, then .cargo/config.toml, then default."""
    raw = str(os.environ.get('CARGO_TARGET_DIR', '') or '').strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = (_CRATE_DIR / p).resolve()
        return p
    # Check .cargo/config.toml for target-dir
    config_toml = _CRATE_DIR / '.cargo' / 'config.toml'
    if config_toml.exists():
        try:
            import re as _re
            text = config_toml.read_text(encoding='utf-8')
            m = _re.search(r'target-dir\s*=\s*"([^"]+)"', text)
            if m:
                p = Path(m.group(1))
                if not p.is_absolute():
                    p = (_CRATE_DIR / p).resolve()
                return p
        except Exception:
            pass
    return _CRATE_DIR / 'target'


def build_rscore(
    release=True,
    show_progress=True,
    idle_timeout=60.0,
    max_timeout=300.0,
    progress_cb=None,
):
    """Build the Rust crate and copy the resulting DLL to the native bin dir.

    Returns a result dict matching the shape used by build_native.py so it
    can be merged into the same ``native-build`` output.
    """
    started = time.monotonic()

    def _emit(evt):
        if callable(progress_cb):
            try:
                progress_cb(evt)
            except Exception:
                pass

    _emit({'type': 'build-start', 'target': _LIB_NAME})

    cargo = _find_cargo()
    if cargo is None:
        msg = ('cargo not found. Install Rust from https://rustup.rs/ '
               'or add ~/.cargo/bin to PATH.')
        _emit({'type': 'build-end', 'ok': False, 'target': _LIB_NAME, 'message': msg})
        return {
            'ok': False,
            'status': 'cargo-missing',
            'compiler': None,
            'output': None,
            'logs': [msg],
        }

    profile = 'release' if release else 'dev'
    # Build the ctypes-facing C ABI library without the PyO3 module glue.
    # This keeps the cargo path portable across macOS while maturin still owns wheel builds.
    cmd = [cargo, 'build', '--manifest-path', str(_CRATE_DIR / 'Cargo.toml'), '--no-default-features']
    if release:
        cmd.append('--release')

    if show_progress:
        print('[rscore] cargo build start profile={}'.format(profile), flush=True)
    _emit({'type': 'target-start', 'target': _LIB_NAME, 'compiler': 'cargo'})

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(_CRATE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as exc:
        msg = 'spawn-failed: {}'.format(exc)
        _emit({'type': 'build-end', 'ok': False, 'target': _LIB_NAME, 'message': msg})
        return {'ok': False, 'status': 'spawn-failed', 'compiler': 'cargo', 'output': None, 'logs': [msg]}

    logs = []
    last_output = time.monotonic()
    for line in proc.stdout:
        line = line.rstrip('\r\n')
        if line:
            logs.append(line)
            last_output = time.monotonic()
            if show_progress:
                print('[rscore] {}'.format(line), flush=True)
            _emit({'type': 'compiler-line', 'target': _LIB_NAME, 'line': line,
                   'elapsed_s': round(time.monotonic() - started, 3)})
        now = time.monotonic()
        if idle_timeout > 0 and (now - last_output) > idle_timeout:
            proc.kill()
            return {'ok': False, 'status': 'idle-timeout', 'compiler': 'cargo', 'output': None, 'logs': logs}
        if max_timeout > 0 and (now - started) > max_timeout:
            proc.kill()
            return {'ok': False, 'status': 'max-timeout', 'compiler': 'cargo', 'output': None, 'logs': logs}

    code = proc.wait()
    elapsed = round(time.monotonic() - started, 3)
    _emit({'type': 'target-exit', 'target': _LIB_NAME, 'exit_code': code, 'elapsed_s': elapsed})

    if code != 0:
        _emit({'type': 'build-end', 'ok': False, 'elapsed_s': elapsed})
        return {'ok': False, 'status': 'cargo-failed', 'compiler': 'cargo', 'output': None, 'logs': logs}

    # Locate the produced artefact.
    profile_dir = 'release' if release else 'debug'
    target_root = _cargo_target_root()
    src = target_root / profile_dir / _cargo_lib_filename()
    if not src.exists():
        msg = (
            'build succeeded but artefact not found: {} '
            '(CARGO_TARGET_DIR={})'
        ).format(src, os.environ.get('CARGO_TARGET_DIR', '<unset>'))
        logs.append(msg)
        _emit({'type': 'build-end', 'ok': False, 'elapsed_s': elapsed, 'message': msg})
        return {'ok': False, 'status': 'artefact-missing', 'compiler': 'cargo', 'output': None, 'logs': logs}

    _NATIVE_BIN.mkdir(parents=True, exist_ok=True)
    dest = _NATIVE_BIN / (_LIB_NAME + _shared_ext())
    tmp = _NATIVE_BIN / (_LIB_NAME + '.tmp' + _shared_ext())

    try:
        shutil.copy2(str(src), str(tmp))
        shutil.move(str(tmp), str(dest))
    except (PermissionError, OSError) as exc:
        note = 'DLL built but locked ({}) – restart Python to apply: {}'.format(exc, dest)
        logs.append(note)
        if show_progress:
            print('[rscore] {}'.format(note), flush=True)
        dest = tmp

    if show_progress:
        print('[rscore] done output={}'.format(dest), flush=True)
    _emit({'type': 'build-end', 'ok': True, 'elapsed_s': elapsed})
    return {
        'ok': True,
        'status': 'ok',
        'compiler': 'cargo',
        'output': str(dest),
        'command': ' '.join(str(c) for c in cmd),
        'logs': logs,
    }


if __name__ == '__main__':
    result = build_rscore(show_progress=True)
    print('rscore build:', 'ok' if result.get('ok') else 'failed')
    if result.get('output'):
        print('  output:', result['output'])
    sys.exit(0 if result.get('ok') else 1)

