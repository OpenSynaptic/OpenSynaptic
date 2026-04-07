import json
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'src' / 'main.py'
CFG = ROOT / 'Config.json'
PY = sys.executable


def _prepare_isolated_config() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    tmp_root = tempfile.TemporaryDirectory(prefix='opensynaptic-cli-')
    tmp_dir = Path(tmp_root.name)
    cfg_path = tmp_dir / 'Config.json'
    shutil.copy2(CFG, cfg_path)

    try:
        cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    except Exception:
        cfg = {}

    resources = cfg.setdefault('RESOURCES', {})
    resources['registry'] = str((tmp_dir / 'device_registry').as_posix())

    security = cfg.setdefault('security_settings', {})
    security['secure_session_store'] = str((tmp_dir / 'secure_sessions.json').as_posix())
    lease = security.setdefault('id_lease', {})
    lease['persist_file'] = str((tmp_dir / 'id_allocation.json').as_posix())

    cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
    return tmp_root, cfg_path


def build_cases(cfg_path: Path):
    cfg_str = str(cfg_path)
    return [
        ('help', ['help'], True),
        ('status', ['status', '--config', cfg_str], True),
        ('id-info', ['id-info', '--config', cfg_str], True),
        ('snapshot', ['snapshot', '--config', cfg_str], True),
        ('pipeline-info', ['pipeline-info', '--config', cfg_str], True),
        ('transport-status', ['transport-status', '--config', cfg_str], True),
        ('db-status', ['db-status', '--config', cfg_str], False),
        ('config-show', ['config-show', '--config', cfg_str], True),
        ('config-get', ['config-get', '--config', cfg_str, '--key', 'engine_settings.precision'], True),
        ('config-set', ['config-set', '--config', cfg_str, '--key', 'engine_settings.precision', '--value', '4', '--type', 'int'], True),
        ('core', ['core', '--config', cfg_str, '--json'], True),
        ('log-level', ['log-level', '--set', 'info'], True),
        ('decode', ['decode', '--format', 'hex', '--data', '3f010000000000000000'], False),
        ('plugin-list', ['plugin-list', '--config', cfg_str], True),
        ('plugin-load', ['plugin-load', '--config', cfg_str, '--name', 'tui'], True),
        ('plugin-cmd:tui:render', ['plugin-cmd', '--config', cfg_str, '--plugin', 'tui', '--cmd', 'render', '--', '--section', 'identity'], True),
        ('plugin-cmd:test_plugin:stress', ['plugin-cmd', '--config', cfg_str, '--plugin', 'test_plugin', '--cmd', 'stress', '--', '--total', '100', '--workers', '2', '--no-progress', '--pipeline-mode', 'batch_fused'], True),
        ('web-user:status', ['web-user', '--config', cfg_str, 'status'], True),
        ('deps:check', ['deps', '--config', cfg_str, 'check'], True),
        ('env-guard:status', ['env-guard', '--config', cfg_str, 'status'], True),
        ('transporter-toggle', ['transporter-toggle', '--config', cfg_str, '--name', 'udp', '--enable'], True),
        ('reload-protocol', ['reload-protocol', '--config', cfg_str, '--medium', 'udp'], False),
        ('transmit', ['transmit', '--config', cfg_str, '--sensor-id', 'V1', '--sensor-status', 'OK', '--value', '1.23', '--unit', 'Pa', '--medium', 'UDP'], True),
        ('inject', ['inject', '--config', cfg_str, '--module', 'compress', '--value', '1.23', '--unit', 'Pa'], True),
        ('time-sync', ['time-sync', '--config', cfg_str, '--host', '127.0.0.1', '--port', '8080'], False),
        ('ensure-id', ['ensure-id', '--config', cfg_str, '--host', '127.0.0.1', '--port', '8080'], False),
        ('native-check', ['native-check'], True),
        ('native-build', ['native-build'], True),
        ('rscore-build', ['rscore-build'], True),
        ('rscore-check', ['rscore-check'], True),
        ('plugin-test:component', ['plugin-test', '--config', cfg_str, '--suite', 'component'], False),
        ('plugin-test:stress', ['plugin-test', '--config', cfg_str, '--suite', 'stress', '--total', '100', '--workers', '2', '--no-progress', '--pipeline-mode', 'batch_fused'], True),
        ('diagnose', ['diagnose', '--config', cfg_str], True),
        ('doctor', ['doctor', '--config', cfg_str], True),
        ('repair-config', ['repair-config', '--config', cfg_str], True),
        ('watch', ['watch', '--config', cfg_str, '--module', 'pipeline', '--interval', '0.2', '--duration', '0.6'], True),
        ('run', ['run', '--config', cfg_str, '--once'], True),
        ('receive-help', ['receive', '--help'], True),
        ('demo-help', ['demo', '--help'], True),
        ('wizard-help', ['wizard', '--help'], True),
        ('init-help', ['init', '--help'], True),
        ('tui', ['tui', '--config', cfg_str, '--section', 'identity'], True),
    ]


def _case_timeout_seconds(name: str) -> int:
    if name == 'native-build':
        return 120
    if name == 'rscore-build':
        return 300
    if name == 'rscore-check':
        return 60
    if name == 'plugin-test:component':
        return 120
    if name == 'plugin-cmd:test_plugin:stress':
        return 60
    return 20


def run_case(name: str, args: list[str], expect_success: bool):
    cmd = [PY, '-u', str(MAIN), '--no-wizard'] + args
    timeout_s = _case_timeout_seconds(name)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        ok = not expect_success
        return {
            'name': name,
            'ok': ok,
            'expected_success': expect_success,
            'returncode': -1,
            'error': f'timeout after {timeout_s}s: {exc}',
            'stdout_tail': ((exc.stdout or '')[-600:] if isinstance(exc.stdout, str) else ''),
            'stderr_tail': ((exc.stderr or '')[-600:] if isinstance(exc.stderr, str) else ''),
            'args': args,
        }
    except Exception as exc:
        return {
            'name': name,
            'ok': False,
            'expected_success': expect_success,
            'returncode': -1,
            'error': str(exc),
            'args': args,
        }

    ok = (proc.returncode == 0) if expect_success else True
    return {
        'name': name,
        'ok': ok,
        'expected_success': expect_success,
        'returncode': proc.returncode,
        'args': args,
        'stdout_tail': (proc.stdout or '')[-600:],
        'stderr_tail': (proc.stderr or '')[-600:],
    }


def main():
    tmp_root, cfg_path = _prepare_isolated_config()
    results = []
    cases = build_cases(cfg_path)
    try:
        for i, (name, args, expect_success) in enumerate(cases, start=1):
            print(f'[{i}/{len(cases)}] {name}')
            row = run_case(name, args, expect_success)
            results.append(row)
            print('  OK' if row['ok'] else f"  FAIL rc={row['returncode']}")
    finally:
        tmp_root.cleanup()

    failed = [r for r in results if not r['ok']]
    out = {
        'total': len(results),
        'passed': len(results) - len(failed),
        'failed': len(failed),
        'failed_cases': failed,
    }

    out_path = ROOT / 'data' / 'benchmarks' / 'cli_exhaustive_report.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\nReport: {out_path}')

    if failed:
        print('\nFailed cases:')
        for r in failed:
            print(f"- {r['name']} (rc={r['returncode']})")
        sys.exit(1)

    print('\nAll CLI cases passed.')


if __name__ == '__main__':
    main()

