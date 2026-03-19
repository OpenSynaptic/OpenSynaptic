import argparse
import importlib.metadata
import json
import re
import subprocess
import sys
from pathlib import Path


try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None


class DependencyManagerPlugin:
    """Dependency inspection and repair plugin."""

    def __init__(self, node=None):
        self.node = node
        self._base_dir = Path(getattr(node, 'base_dir', Path(__file__).resolve().parents[4]))

    @staticmethod
    def get_required_config():
        return {
            'enabled': True,
            'mode': 'manual',
            'auto_repair': False,
        }

    def auto_load(self):
        return self

    def _pyproject_dependencies(self):
        pyproject = self._base_dir / 'pyproject.toml'
        if not pyproject.exists():
            return []
        text = pyproject.read_bytes()
        if tomllib is not None:
            data = tomllib.loads(text.decode('utf-8'))
        else:
            import toml  # fallback package already listed in dependencies
            data = toml.loads(text.decode('utf-8'))
        deps = data.get('project', {}).get('dependencies', [])
        return [str(item).strip() for item in deps if str(item).strip()]

    @staticmethod
    def _extract_name(requirement):
        # Handles common requirement forms: pkg, pkg>=1.0, pkg[extra], pkg==x
        token = re.split(r'[<>=!~; ]', str(requirement).strip(), maxsplit=1)[0]
        token = token.split('[', 1)[0].strip()
        return token

    def _inspect(self):
        declared = self._pyproject_dependencies()
        details = []
        missing = []
        for dep in declared:
            name = self._extract_name(dep)
            if not name:
                continue
            try:
                installed = importlib.metadata.version(name)
                details.append({'requirement': dep, 'name': name, 'installed': installed, 'ok': True})
            except importlib.metadata.PackageNotFoundError:
                details.append({'requirement': dep, 'name': name, 'installed': None, 'ok': False})
                missing.append(dep)
        return {
            'declared_total': len(declared),
            'missing_total': len(missing),
            'missing': missing,
            'details': details,
        }

    def _run_pip(self, args):
        cmd = [sys.executable, '-m', 'pip'] + list(args)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return {
            'command': cmd,
            'return_code': proc.returncode,
            'stdout': proc.stdout.strip(),
            'stderr': proc.stderr.strip(),
            'ok': proc.returncode == 0,
        }

    def _repair_missing(self, allow_upgrade=False):
        report = self._inspect()
        missing = report.get('missing', [])
        actions = []
        if not missing:
            return {'ok': True, 'actions': [], 'report': report}
        for dep in missing:
            args = ['install', dep]
            if allow_upgrade:
                args.insert(1, '--upgrade')
            actions.append(self._run_pip(args))
        new_report = self._inspect()
        ok = new_report.get('missing_total', 0) == 0
        return {'ok': ok, 'actions': actions, 'report': new_report}

    def get_cli_commands(self):
        def _check(argv):
            _ = argv
            payload = self._inspect()
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0 if payload.get('missing_total', 0) == 0 else 1

        def _doctor(argv):
            _ = argv
            payload = self._run_pip(['check'])
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0 if payload.get('ok') else 1

        def _sync(argv):
            p = argparse.ArgumentParser(prog='dependency_manager sync')
            p.add_argument('--upgrade', action='store_true', default=False)
            ns = p.parse_args(argv)
            deps = self._pyproject_dependencies()
            actions = []
            for dep in deps:
                args = ['install', dep]
                if ns.upgrade:
                    args.insert(1, '--upgrade')
                actions.append(self._run_pip(args))
            ok = all(a.get('ok') for a in actions) if actions else True
            result = {'ok': ok, 'actions': actions, 'declared_total': len(deps)}
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if ok else 1

        def _repair(argv):
            p = argparse.ArgumentParser(prog='dependency_manager repair')
            p.add_argument('--upgrade', action='store_true', default=False)
            ns = p.parse_args(argv)
            result = self._repair_missing(allow_upgrade=ns.upgrade)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result.get('ok') else 1

        def _install(argv):
            p = argparse.ArgumentParser(prog='dependency_manager install')
            p.add_argument('--name', required=True)
            p.add_argument('--upgrade', action='store_true', default=False)
            ns = p.parse_args(argv)
            args = ['install', ns.name]
            if ns.upgrade:
                args.insert(1, '--upgrade')
            result = self._run_pip(args)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result.get('ok') else 1

        return {
            'check': _check,
            'doctor': _doctor,
            'sync': _sync,
            'repair': _repair,
            'install': _install,
        }

