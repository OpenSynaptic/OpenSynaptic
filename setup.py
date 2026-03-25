from pathlib import Path
import os
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

try:
    from setuptools.command.install import install as _install
except Exception:  # pragma: no cover
    _install = None

try:
    from wheel.bdist_wheel import bdist_wheel as _bdist_wheel
except Exception:  # pragma: no cover
    _bdist_wheel = None


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


def _run_rscore_build():
    root = Path(__file__).resolve().parent
    script = root / 'src' / 'opensynaptic' / 'core' / 'rscore' / 'build_rscore.py'
    if not script.exists():
        if _require_rscore_for_build():
            raise SystemExit('rscore build script not found: {}'.format(script))
        return

    strict = _require_rscore_for_build()
    try:
        subprocess.run([sys.executable, str(script)], check=strict, cwd=str(root))
    except Exception:
        if strict:
            raise
        return
    # Keep package payload clean: ship only final os_rscore.* files, not temp lock artifacts.
    bin_dir = root / 'src' / 'opensynaptic' / 'utils' / 'c' / 'bin'
    if not bin_dir.exists():
        if strict:
            raise SystemExit('rscore output directory not found: {}'.format(bin_dir))
        return

    final_lib = bin_dir / ('os_rscore' + _platform_shared_ext())
    if strict and not final_lib.exists():
        raise SystemExit('required rscore library missing after build: {}'.format(final_lib))

    for ext in ('.dll', '.so', '.dylib'):
        final_lib = bin_dir / ('os_rscore' + ext)
        tmp_lib = bin_dir / ('os_rscore.tmp' + ext)
        if final_lib.exists() and tmp_lib.exists():
            try:
                tmp_lib.unlink()
            except Exception:
                pass


def _platform_shared_ext():
    if os.name == 'nt':
        return '.dll'
    if sys.platform.startswith('darwin'):
        return '.dylib'
    return '.so'


def _require_rscore_for_build():
    val = os.getenv('OPENSYNAPTIC_REQUIRE_RSCORE', '0').strip().lower()
    return val in {'1', 'true', 'yes', 'on'}


def _print_post_install_banner():
    lines = [
        '',
        'OpenSynaptic installed successfully.',
        'Quick start:',
        '  os-node demo',
        '  os-node --help',
        'Docs:   https://github.com/OpenSynaptic/OpenSynaptic#readme',
        'Issues: https://github.com/OpenSynaptic/OpenSynaptic/issues',
        '',
    ]
    try:
        sys.stdout.write('\n'.join(lines) + '\n')
    except Exception:
        pass


class BuildPyWithNative(_build_py):

    def run(self):
        _run_native_build()
        _run_rscore_build()
        super().run()


if _bdist_wheel is not None:

    class BDistWheelNonPure(_bdist_wheel):

        def finalize_options(self):
            super().finalize_options()
            # opensynaptic bundles platform native libs under opensynaptic/utils/c/bin
            self.root_is_pure = False
else:
    BDistWheelNonPure = None


if _install is not None:

    class InstallWithBanner(_install):

        def run(self):
            super().run()
            _print_post_install_banner()
else:
    InstallWithBanner = None


if _develop is not None:

    class DevelopWithNative(_develop):

        def run(self):
            _run_native_build()
            super().run()
            _print_post_install_banner()

    _cmdclass = {'build_py': BuildPyWithNative, 'develop': DevelopWithNative}
else:
    _cmdclass = {'build_py': BuildPyWithNative}

if InstallWithBanner is not None:
    _cmdclass['install'] = InstallWithBanner
if BDistWheelNonPure is not None:
    _cmdclass['bdist_wheel'] = BDistWheelNonPure


if len(sys.argv) == 1:
    # Show usage help instead of failing with "no commands supplied".
    sys.argv.append('--help')


setup(cmdclass=_cmdclass)
