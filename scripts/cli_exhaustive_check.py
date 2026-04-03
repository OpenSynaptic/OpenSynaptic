import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'src' / 'main.py'
CFG = ROOT / 'Config.json'
PY = sys.executable

# Each entry: (name, args, expect_success)
CASES = [
    ('help', ['help'], True),
    ('status', ['status', '--config', str(CFG)], True),
    ('id-info', ['id-info', '--config', str(CFG)], True),
    ('snapshot', ['snapshot', '--config', str(CFG)], True),
    ('pipeline-info', ['pipeline-info', '--config', str(CFG)], True),
    ('transport-status', ['transport-status', '--config', str(CFG)], True),
    ('db-status', ['db-status', '--config', str(CFG)], False),
    ('config-show', ['config-show', '--config', str(CFG)], True),
    ('config-get', ['config-get', '--config', str(CFG), '--key', 'engine_settings.precision'], True),
    ('config-set', ['config-set', '--config', str(CFG), '--key', 'engine_settings.precision', '--value', '4', '--type', 'int'], True),
    ('core', ['core', '--config', str(CFG), '--json'], True),
    ('log-level', ['log-level', '--set', 'info'], True),
    ('decode', ['decode', '--format', 'hex', '--data', '3f010000000000000000'], False),
    ('plugin-list', ['plugin-list', '--config', str(CFG)], True),
    ('plugin-load', ['plugin-load', '--config', str(CFG), '--name', 'tui'], True),
    ('plugin-cmd:tui:render', ['plugin-cmd', '--config', str(CFG), '--plugin', 'tui', '--cmd', 'render', '--', '--section', 'identity'], True),
    ('plugin-cmd:test_plugin:stress', ['plugin-cmd', '--config', str(CFG), '--plugin', 'test_plugin', '--cmd', 'stress', '--', '--total', '100', '--workers', '2', '--no-progress', '--pipeline-mode', 'batch_fused'], True),
    ('web-user:status', ['web-user', '--config', str(CFG), 'status'], True),
    ('deps:check', ['deps', '--config', str(CFG), 'check'], True),
    ('env-guard:status', ['env-guard', '--config', str(CFG), 'status'], True),
    ('transporter-toggle', ['transporter-toggle', '--config', str(CFG), '--name', 'udp', '--enable'], True),
    ('reload-protocol', ['reload-protocol', '--config', str(CFG), '--medium', 'udp'], False),
    ('transmit', ['transmit', '--config', str(CFG), '--sensor-id', 'V1', '--sensor-status', 'OK', '--value', '1.23', '--unit', 'Pa', '--medium', 'UDP'], True),
    ('inject', ['inject', '--config', str(CFG), '--module', 'compress', '--value', '1.23', '--unit', 'Pa'], True),
    ('time-sync', ['time-sync', '--config', str(CFG), '--host', '127.0.0.1', '--port', '8080'], False),
    ('ensure-id', ['ensure-id', '--config', str(CFG), '--host', '127.0.0.1', '--port', '8080'], False),
    ('native-check', ['native-check'], True),
    ('native-build', ['native-build'], True),
    ('rscore-build', ['rscore-build'], True),
    ('rscore-check', ['rscore-check'], True),
    ('plugin-test:component', ['plugin-test', '--config', str(CFG), '--suite', 'component'], False),
    ('plugin-test:stress', ['plugin-test', '--config', str(CFG), '--suite', 'stress', '--total', '100', '--workers', '2', '--no-progress', '--pipeline-mode', 'batch_fused'], True),
    ('diagnose', ['diagnose', '--config', str(CFG)], True),
    ('doctor', ['doctor', '--config', str(CFG)], True),
    ('repair-config', ['repair-config', '--config', str(CFG)], True),
    ('watch', ['watch', '--config', str(CFG), '--module', 'pipeline', '--interval', '0.2', '--duration', '0.6'], True),
    ('run', ['run', '--config', str(CFG), '--once'], True),
    ('receive-help', ['receive', '--help'], True),
    ('demo-help', ['demo', '--help'], True),
    ('wizard-help', ['wizard', '--help'], True),
    ('init-help', ['init', '--help'], True),
    ('tui', ['tui', '--config', str(CFG), '--section', 'identity'], True),
]


def _case_timeout_seconds(name: str) -> int:
    if name == 'native-build':
        return 120
    if name == 'rscore-build':
        return 300
    if name == 'rscore-check':
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
        return {
            'name': name,
            'ok': False,
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
    results = []
    for i, (name, args, expect_success) in enumerate(CASES, start=1):
        print(f'[{i}/{len(CASES)}] {name}')
        row = run_case(name, args, expect_success)
        results.append(row)
        print('  OK' if row['ok'] else f"  FAIL rc={row['returncode']}")

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

