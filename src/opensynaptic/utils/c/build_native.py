import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

ROOT = Path(__file__).resolve().parent
SRC_ROOT = ROOT.parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from opensynaptic.utils.c.check_native_toolchain import build_guidance, get_toolchain_report, pick_compiler

BIN = ROOT / 'bin'
_TARGETS = {
    'os_base62': ROOT.parent / 'base62' / 'base62_native.c',
    'os_security': ROOT.parent / 'security' / 'security_native.c',
}


def _shared_ext():
    if os.name == 'nt':
        return '.dll'
    if sys.platform.startswith('darwin'):
        return '.dylib'
    return '.so'


def _is_cl_compiler(compiler_exe):
    """Return True when the executable is MSVC cl (not clang-cl or gcc)."""
    base = os.path.basename(str(compiler_exe or '')).lower()
    return base in ('cl', 'cl.exe')


def _cl_env_ready():
    """Return True when MSVC include paths are available in the current environment."""
    return bool(os.environ.get('INCLUDE') or os.environ.get('VCINSTALLDIR') or os.environ.get('VSINSTALLDIR'))


def _cmd_for_compiler(compiler_exe, src_path, out_path):
    if _is_cl_compiler(compiler_exe):
        # MSVC-style: /LD (DLL), /Fe sets output, /nologo suppresses banner
        return [
            str(compiler_exe), '/nologo', '/LD', '/O2',
            '/Fe:{}'.format(str(out_path)),
            str(src_path),
        ]
    return [str(compiler_exe), '-shared', '-O3', '-std=c99', str(src_path), '-o', str(out_path)]


def _emit(progress_cb, event):
    if callable(progress_cb):
        try:
            progress_cb(event)
        except Exception:
            return


def _run_compile(cmd, target_name, show_progress=True, idle_timeout=20.0, max_timeout=300.0, progress_cb=None):
    lines = []
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            universal_newlines=True,
            bufsize=1,
        )
    except Exception as exc:
        return False, ['spawn-failed: {}'.format(exc)], 'spawn-failed'

    q = queue.Queue()

    def _reader():
        if proc.stdout is None:
            q.put(None)
            return
        try:
            for raw in proc.stdout:
                q.put(raw)
        finally:
            q.put(None)

    threading.Thread(target=_reader, daemon=True).start()
    started = time.monotonic()
    last_output = started
    done = False

    while not done:
        try:
            item = q.get(timeout=0.25)
        except queue.Empty:
            item = '__tick__'

        now = time.monotonic()
        if item is None:
            done = True
        elif item != '__tick__':
            line = str(item).rstrip('\r\n')
            if line:
                lines.append(line)
                last_output = now
                if show_progress:
                    print('[native][{}] {}'.format(target_name, line), flush=True)
                _emit(progress_cb, {
                    'type': 'compiler-line',
                    'target': target_name,
                    'elapsed_s': round(now - started, 3),
                    'line': line,
                })

        if int(now - started) != int((now - 0.25) - started):
            _emit(progress_cb, {
                'type': 'heartbeat',
                'target': target_name,
                'elapsed_s': round(now - started, 3),
                'idle_s': round(now - last_output, 3),
            })

        if idle_timeout > 0 and (now - last_output) > float(idle_timeout):
            proc.kill()
            msg = 'idle-timeout: no compiler output for {:.1f}s'.format(float(idle_timeout))
            lines.append(msg)
            if show_progress:
                print('[native][{}] {}'.format(target_name, msg), flush=True)
            _emit(progress_cb, {
                'type': 'timeout',
                'target': target_name,
                'elapsed_s': round(now - started, 3),
                'reason': 'idle-timeout',
                'message': msg,
            })
            return False, lines, 'idle-timeout'

        if max_timeout > 0 and (now - started) > float(max_timeout):
            proc.kill()
            msg = 'max-timeout: compile exceeded {:.1f}s'.format(float(max_timeout))
            lines.append(msg)
            if show_progress:
                print('[native][{}] {}'.format(target_name, msg), flush=True)
            _emit(progress_cb, {
                'type': 'timeout',
                'target': target_name,
                'elapsed_s': round(now - started, 3),
                'reason': 'max-timeout',
                'message': msg,
            })
            return False, lines, 'max-timeout'

    code = proc.wait()
    _emit(progress_cb, {
        'type': 'target-exit',
        'target': target_name,
        'elapsed_s': round(time.monotonic() - started, 3),
        'exit_code': int(code),
    })
    return code == 0, lines, 'ok'


def build_all(show_progress=True, idle_timeout=20.0, max_timeout=300.0, progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None):
    BIN.mkdir(parents=True, exist_ok=True)
    started_all = time.monotonic()
    _emit(progress_cb, {'type': 'build-start'})
    report = get_toolchain_report()
    selected = pick_compiler(report)
    result = {
        'precheck': report,
        'guidance': build_guidance(report),
        'selected': selected,
        'targets': {},
        'ok': False,
    }

    # If cl is selected but VS environment isn't initialised (no INCLUDE paths),
    # it will fail to find stdint.h. Fall back to clang or gcc if available.
    if selected == 'cl' and not _cl_env_ready():
        available = list(report.get('available', []))
        fallback = next((c for c in ('clang', 'gcc') if c in available), None)
        if fallback:
            selected = fallback
            exe_info = ((report.get('entries') or {}).get(selected) or {})
            # Update selected_executable later in the flow
            report.setdefault('_fallback_note', 'cl skipped (VS env not initialised); using {}'.format(fallback))

    if not selected:
        for name in _TARGETS:
            result['targets'][name] = {
                'ok': False,
                'compiler': None,
                'output': None,
                'command': None,
                'logs': ['No compiler selected from precheck'],
            }
        _emit(progress_cb, {
            'type': 'build-end',
            'ok': False,
            'elapsed_s': round(time.monotonic() - started_all, 3),
        })
        return result

    selected_executable = ((report.get('entries') or {}).get(selected) or {}).get('executable') if selected else None
    if not selected_executable and selected:
        # Try to find the executable via PATH if entries don't have it
        import shutil
        selected_executable = shutil.which(selected)
    if not selected_executable:
        for name in _TARGETS:
            result['targets'][name] = {
                'ok': False,
                'status': 'missing-compiler-executable',
                'compiler': selected,
                'output': None,
                'command': None,
                'logs': ['Selected compiler has no executable path'],
            }
        _emit(progress_cb, {
            'type': 'build-end',
            'ok': False,
            'elapsed_s': round(time.monotonic() - started_all, 3),
        })
        return result

    for name, src_path in _TARGETS.items():
        out_path = BIN / '{}{}'.format(name, _shared_ext())
        tmp_path = BIN / '{}.tmp{}'.format(name, _shared_ext())
        cmd = _cmd_for_compiler(selected_executable, src_path, tmp_path)
        _emit(progress_cb, {
            'type': 'target-start',
            'target': name,
            'compiler': selected,
            'elapsed_s': round(time.monotonic() - started_all, 3),
        })
        if show_progress:
            print('[native][{}] start compiler={}'.format(name, selected), flush=True)
        ok, logs, status = _run_compile(
            cmd,
            name,
            show_progress=show_progress,
            idle_timeout=idle_timeout,
            max_timeout=max_timeout,
            progress_cb=progress_cb,
        )

        final_path = out_path
        if ok:
            # Atomic replace: try to move tmp -> out_path
            try:
                import shutil as _shutil
                _shutil.move(str(tmp_path), str(out_path))
            except (PermissionError, OSError):
                # Target DLL is locked (loaded by a running process).
                # Keep the .tmp file for the next restart.
                status = 'built-locked'
                final_path = tmp_path
                locked_note = (
                    'DLL built as {} — the existing {} is still loaded. '
                    'Restart Python to apply the update.'.format(tmp_path.name, out_path.name)
                )
                logs.append(locked_note)
                if show_progress:
                    print('[native][{}] {}'.format(name, locked_note), flush=True)
            else:
                # Clean up any leftover .tmp from previous runs
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
        else:
            # Build failed — clean up incomplete tmp
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

        result['targets'][name] = {
            'ok': ok,
            'status': status,
            'compiler': selected,
            'output': str(final_path) if ok else None,
            'command': ' '.join(str(c) for c in cmd),
            'logs': logs,
        }
        if show_progress:
            print('[native][{}] {}'.format(name, 'done' if ok else 'failed'), flush=True)

    result['ok'] = all(
        bool(v.get('ok')) if isinstance(v, dict) else False
        for v in result['targets'].values()
    )
    _emit(progress_cb, {
        'type': 'build-end',
        'ok': bool(result['ok']),
        'elapsed_s': round(time.monotonic() - started_all, 3),
    })
    return result


def _print_summary(result):
    print(result.get('guidance', ''))
    print('selected:', result.get('selected') or 'none')
    for name, info in result.get('targets', {}).items():
        print('{}: {}'.format(name, 'ok' if info.get('ok') else 'build-failed'))
        if info.get('output'):
            print('  output:', info['output'])


if __name__ == '__main__':
    build_result = build_all(show_progress=True)
    _print_summary(build_result)
