from pathlib import Path
import subprocess
import sys


def _run(cmd):
    root = Path(__file__).resolve().parent
    return subprocess.call(cmd, cwd=str(root))


def main(argv=None):
    args = list(argv if argv is not None else sys.argv[1:])
    manifest = str(Path('src') / 'opensynaptic' / 'core' / 'rscore' / 'rust' / 'Cargo.toml')

    if not args or any(a in {'-h', '--help', 'help'} for a in args):
        print('OpenSynaptic now uses maturin-only packaging.')
        print('Use one of:')
        print(f'  {sys.executable} -m maturin develop --manifest-path {manifest}')
        print(f'  {sys.executable} -m maturin build --release --manifest-path {manifest} --out dist')
        print(f'  {sys.executable} -m maturin sdist --manifest-path {manifest} --out dist')
        return 0

    if 'develop' in args:
        return _run([sys.executable, '-m', 'maturin', 'develop', '--manifest-path', manifest])
    if 'sdist' in args:
        return _run([sys.executable, '-m', 'maturin', 'sdist', '--manifest-path', manifest, '--out', 'dist'])

    # Default fallback for legacy setup.py build/install usage.
    return _run([sys.executable, '-m', 'maturin', 'build', '--release', '--manifest-path', manifest, '--out', 'dist'])


if __name__ == '__main__':
    raise SystemExit(main())
