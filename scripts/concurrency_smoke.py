#!/usr/bin/env python
"""
scripts/concurrency_smoke.py
Concurrent pipeline smoke-test for OpenSynaptic.

Usage:
    python scripts/concurrency_smoke.py [total=200] [workers=8] [sources=6]

All arguments are positional and optional (defaults shown above).
Exit code: 0 = all passed, 1 = failures detected.

Example:
    python scripts/concurrency_smoke.py 500 16 8
"""
import json
import sys
from pathlib import Path

# Ensure the project root and src/ are importable
_ROOT = None
for _p in Path(__file__).resolve().parents:
    if (_p / 'Config.json').exists():
        _ROOT = str(_p)
        break

if _ROOT:
    _src = str(Path(_ROOT) / 'src')
    if _src not in sys.path:
        sys.path.insert(0, _src)
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)


def _parse_args():
    defaults = {'total': 200, 'workers': 8, 'sources': 6}
    argv = sys.argv[1:]
    keys = ['total', 'workers', 'sources']
    for i, val in enumerate(argv[:3]):
        try:
            defaults[keys[i]] = int(val)
        except ValueError:
            print('[smoke] 無效參數 {!r}，使用預設值 {}'.format(val, defaults[keys[i]]))
    return defaults


def main():
    params = _parse_args()
    print('[smoke] 啟動壓力測試  total={total}  workers={workers}  sources={sources}'.format(**params))

    from opensynaptic.services.test_plugin.stress_tests import run_stress
    result, summary = run_stress(
        total=params['total'],
        workers=params['workers'],
        sources=params['sources'],
        progress=True,
    )

    print('\n[smoke] 結果摘要:')
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    if result.fail > 0:
        print('\n[smoke] ❌  {} 次失敗。抽樣錯誤:'.format(result.fail))
        for err in result.errors[:5]:
            print('  •', err)
        sys.exit(1)
    else:
        print('\n[smoke] ✅  全部通過！吞吐量 {} pps'.format(summary.get('throughput_pps', '?')))
        sys.exit(0)


if __name__ == '__main__':
    main()

