import glob
import os
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional


_COMPILERS = ('cl', 'gcc', 'clang')

# Well-known installation paths per compiler on Windows.
# These are checked as a fallback when PATH lookup fails so that
# tools installed but not yet on PATH (e.g. right after install,
# before the terminal is restarted) are still found.
_WINDOWS_FALLBACK_GLOBS: Dict[str, List[str]] = {
    'clang': [
        r'C:\Program Files\LLVM\bin\clang.exe',
        r'C:\Program Files (x86)\LLVM\bin\clang.exe',
        r'C:\msys64\ucrt64\bin\clang.exe',
        r'C:\msys64\mingw64\bin\clang.exe',
    ],
    'gcc': [
        r'C:\msys64\ucrt64\bin\gcc.exe',
        r'C:\msys64\mingw64\bin\gcc.exe',
        r'C:\mingw64\bin\gcc.exe',
        r'C:\mingw32\bin\gcc.exe',
    ],
    'cl': [
        # VS 2022 / 2019 / 2017 community/professional/enterprise
        r'C:\Program Files\Microsoft Visual Studio\*\*\VC\Tools\MSVC\*\bin\Hostx64\x64\cl.exe',
        r'C:\Program Files (x86)\Microsoft Visual Studio\*\*\VC\Tools\MSVC\*\bin\Hostx64\x64\cl.exe',
        r'D:\Visual Studio\VC\Tools\MSVC\*\bin\Hostx64\x64\cl.exe',
    ],
}


def _emit(progress_cb: Optional[Callable[[Dict[str, Any]], None]], event: Dict[str, Any]) -> None:
    if not callable(progress_cb):
        return
    try:
        progress_cb(event)
    except Exception:
        return


def _find_in_known_paths(name: str) -> Optional[str]:
    """Scan well-known installation directories for a compiler executable."""
    if os.name != 'nt':
        return None
    for pattern in _WINDOWS_FALLBACK_GLOBS.get(name, []):
        if '*' in pattern:
            matches = sorted(glob.glob(pattern), reverse=True)  # newest first
            for match in matches:
                if os.path.isfile(match):
                    return match
        elif os.path.isfile(pattern):
            return pattern
    return None


def _detect_executable(name: str, timeout_s: float) -> Optional[str]:
    if os.name == 'nt':
        cmd = ['where', name]
    else:
        cmd = ['sh', '-lc', 'command -v {}'.format(name)]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(0.2, float(timeout_s)),
        )
    except Exception:
        proc = None

    if proc is not None and proc.returncode == 0:
        text = (proc.stdout or '').strip()
        for line in text.splitlines():
            val = line.strip()
            if val:
                return val

    # PATH lookup failed — try well-known install locations
    return _find_in_known_paths(name)


def _probe_version(name: str, executable: str, timeout_s: float) -> str:
    if not executable:
        return ''
    cmd = [executable, '--version']
    if name == 'cl':
        cmd = [executable, '/?']
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=max(0.2, float(timeout_s)),
        )
    except Exception:
        return ''
    text = '\n'.join([proc.stdout or '', proc.stderr or '']).strip()
    if not text:
        return ''
    for line in text.splitlines():
        val = line.strip()
        if val:
            return val
    return ''


def _compiler_from_override(override: str) -> Optional[str]:
    low = str(override or '').strip().lower()
    if low in _COMPILERS:
        return low
    base = os.path.basename(low)
    if base.startswith('cl'):
        return 'cl'
    if base.startswith('gcc'):
        return 'gcc'
    if base.startswith('clang'):
        return 'clang'
    return None


def get_toolchain_report(
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    detect_timeout: float = 1.5,
    version_timeout: float = 1.5,
    overall_timeout: float = 8.0,
) -> Dict[str, Any]:
    t0 = time.monotonic()
    _emit(progress_cb, {'type': 'step', 'step': 'precheck-start', 'elapsed_s': 0.0})

    if os.name == 'nt':
        system = 'windows'
    elif sys.platform.startswith('darwin'):
        system = 'darwin'
    else:
        system = 'linux'
    override_raw = str(os.environ.get('OPENSYNAPTIC_CC', '')).strip()
    override = override_raw.lower()
    _emit(progress_cb, {'type': 'step', 'step': 'platform-detected', 'platform': system, 'override': override_raw})

    entries: Dict[str, Dict[str, Any]] = {}
    available = []
    timed_out = False
    last_step = 'platform-detected'

    for name in _COMPILERS:
        elapsed = time.monotonic() - t0
        if elapsed >= float(overall_timeout):
            timed_out = True
            last_step = 'overall-timeout'
            break

        last_step = 'compiler-check-start'
        _emit(progress_cb, {'type': 'step', 'step': 'compiler-check-start', 'compiler': name, 'elapsed_s': round(elapsed, 3)})

        executable = _detect_executable(name, timeout_s=detect_timeout)
        env_hint = None
        if name == 'cl':
            env_hint = str(os.environ.get('VCINSTALLDIR', '') or os.environ.get('VSINSTALLDIR', '')).strip() or None
        elif name in ('gcc', 'clang'):
            env_hint = str(os.environ.get('CC', '')).strip() or None

        is_available = bool(executable)
        if is_available:
            available.append(name)

        entries[name] = {
            'executable': executable,
            'env_hint': env_hint,
            'available': is_available,
            'version': '',
        }

        last_step = 'compiler-check-end'
        _emit(progress_cb, {
            'type': 'step',
            'step': 'compiler-check-end',
            'compiler': name,
            'executable': executable,
            'elapsed_s': round(time.monotonic() - t0, 3),
        })

    selected = None
    override_compiler = _compiler_from_override(override)
    if override_compiler:
        if os.path.isabs(override_raw) and os.path.exists(override_raw):
            selected = override_compiler
            entries[selected]['executable'] = override_raw
            entries[selected]['available'] = True
            if selected not in available:
                available.append(selected)
        elif entries.get(override_compiler, {}).get('available'):
            selected = override_compiler
    if not selected:
        for name in _COMPILERS:
            if entries.get(name, {}).get('available'):
                selected = name
                break

    if selected and entries.get(selected, {}).get('executable'):
        last_step = 'probe-version-start'
        _emit(progress_cb, {'type': 'step', 'step': 'probe-version-start', 'compiler': selected, 'elapsed_s': round(time.monotonic() - t0, 3)})
        entries[selected]['version'] = _probe_version(selected, entries[selected]['executable'], timeout_s=version_timeout)
        last_step = 'probe-version-end'
        _emit(progress_cb, {'type': 'step', 'step': 'probe-version-end', 'compiler': selected, 'elapsed_s': round(time.monotonic() - t0, 3)})

    report = {
        'platform': system,
        'override': override_raw,
        'entries': entries,
        'available': available,
        'selected': selected,
        'ok': bool(selected) and not timed_out,
        'timeout': bool(timed_out),
        'last_step': last_step,
        'elapsed_s': round(time.monotonic() - t0, 3),
    }
    _emit(progress_cb, {'type': 'step', 'step': 'precheck-end', 'ok': report['ok'], 'elapsed_s': report['elapsed_s']})
    return report


def pick_compiler(report: Optional[Dict[str, Any]] = None) -> Optional[str]:
    rep = report or get_toolchain_report()
    selected = str(rep.get('selected') or '').strip().lower()
    return selected or None


def build_guidance(report: Optional[Dict[str, Any]] = None) -> str:
    rep = report or get_toolchain_report()
    if rep.get('timeout'):
        return 'Toolchain precheck timeout at step [{}] after {}s'.format(rep.get('last_step', 'unknown'), rep.get('elapsed_s', '?'))
    if rep.get('ok'):
        return 'Compiler ready: {}'.format(rep.get('selected'))
    if os.name == 'nt':
        return 'No compiler detected. Install cl/gcc/clang or set OPENSYNAPTIC_CC to an executable path.'
    return 'No compiler detected. Install gcc/clang or set OPENSYNAPTIC_CC.'


def print_report() -> None:
    rep = get_toolchain_report()
    print('platform:', rep['platform'])
    print('override:', rep.get('override') or 'none')
    print('selected:', rep.get('selected') or 'none')
    print('timeout:', rep.get('timeout'))
    print('elapsed_s:', rep.get('elapsed_s'))
    for name in _COMPILERS:
        info = rep['entries'].get(name, {})
        print('{}: {}'.format(name, info.get('executable') or 'not-found'))
        if info.get('env_hint'):
            print('  hint:', info['env_hint'])
        if info.get('version'):
            print('  version:', info['version'])
    print(build_guidance(rep))


if __name__ == '__main__':
    print_report()
