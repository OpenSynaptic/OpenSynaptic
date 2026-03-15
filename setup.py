from pathlib import Path
import subprocess
import sys

try:
    from setuptools import setup
    from setuptools.command.build_py import build_py as _build_py
except ModuleNotFoundError as exc:  # pragma: no cover
    if getattr(exc, 'name', '') == 'setuptools':
        raise SystemExit(
            'Missing dependency: setuptools. '\
            'Install it with: python -m pip install -U setuptools wheel'
        )
    raise

try:
    from setuptools.command.develop import develop as _develop
except Exception:  # pragma: no cover
    _develop = None


def _run_native_build():
    root = Path(__file__).resolve().parent
    script = root / 'src' / 'opensynaptic' / 'utils' / 'c' / 'build_native.py'
    if not script.exists():
        return
    try:
        subprocess.run([sys.executable, str(script)], check=False, cwd=str(root))
    except Exception:
        # Native build is best-effort for packaging step.
        return


class BuildPyWithNative(_build_py):

    def run(self):
        _run_native_build()
        super().run()


if _develop is not None:

    class DevelopWithNative(_develop):

        def run(self):
            _run_native_build()
            super().run()

    _cmdclass = {'build_py': BuildPyWithNative, 'develop': DevelopWithNative}
else:
    _cmdclass = {'build_py': BuildPyWithNative}


if len(sys.argv) == 1:
    # Show usage help instead of failing with "no commands supplied".
    sys.argv.append('--help')


setup(cmdclass=_cmdclass)

