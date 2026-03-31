"""
dependency_manager - 依赖管理插件

功能：
    - 检查和修复项目依赖
    - 自动安装缺失的包
    - 生成依赖报告
    - CLI 命令支持

2026 M03 规范：
    - __init__ 接受 node 和 **kwargs
    - get_required_config() 返回完整配置
    - auto_load() 初始化资源
    - close() 清理资源
    - 所有操作线程安全
"""
import argparse
import importlib.metadata
import json
import re
import subprocess
import sys
import threading
from pathlib import Path

from opensynaptic.utils import os_log, LogMsg
from opensynaptic.services.display_api import DisplayProvider, get_display_registry


try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None


class DependencyManagerDisplayProvider(DisplayProvider):
    """Display dependency manager status for unified dashboard."""

    def __init__(self, plugin_ref):
        super().__init__(plugin_name='dependency_manager', section_id='status', display_name='Dependency Manager Status')
        self.category = 'plugin'
        self.priority = 66
        self.refresh_interval_s = 8.0
        self._plugin = plugin_ref

    def extract_data(self, node=None, **kwargs):
        _ = node, kwargs
        plugin = self._plugin
        report = None
        with plugin._lock:
            report = dict(plugin._last_report or {}) if isinstance(plugin._last_report, dict) else None
            initialized = bool(plugin._initialized)
        if report is None:
            try:
                report = plugin._inspect()
            except Exception:
                report = {'error': 'inspect failed'}
        return {
            'initialized': initialized,
            'auto_repair': bool((plugin.config or {}).get('auto_repair', False)),
            'report': report,
        }


class DependencyManagerPlugin:
    """依赖管理和修复插件
    
    线程安全：是（使用 self._lock）
    Display Providers：dependency_manager:status
    """

    def __init__(self, node=None, **kwargs):
        """初始化依赖管理插件（按 2026 规范）
        
        参数：
            node: OpenSynaptic 节点实例
            **kwargs: 配置字典
        """
        self.node = node
        self.config = kwargs or {}
        self._lock = threading.Lock()
        
        self._base_dir = Path(getattr(node, 'base_dir', Path(__file__).resolve().parents[4]))
        
        # 状态
        self._initialized = False
        self._last_report = None
        
        os_log.log_with_const('info', LogMsg.PLUGIN_INIT, 
                             plugin='DependencyManager')

    @staticmethod
    def get_required_config():
        """返回默认配置（按 2026 规范）"""
        return {
            'enabled': True,
            'mode': 'manual',
            'auto_repair': False,
        }

    def auto_load(self, config=None):
        """自动加载钩子（按 2026 规范）"""
        if config:
            self.config = config
        
        if not self.config.get('enabled', True):
            return self
        
        try:
            with self._lock:
                self._initialized = True
                self._last_report = self._inspect()
                reg = get_display_registry()
                reg.unregister('dependency_manager', 'status')
                reg.register(DependencyManagerDisplayProvider(self))
                os_log.log_with_const('info', LogMsg.PLUGIN_READY, 
                                     plugin='DependencyManager')
        except Exception as exc:
            os_log.err('DEPENDENCY_MGR', 'LOAD_FAILED', exc, {})
            self._initialized = False
        
        return self

    def close(self):
        """清理资源（按 2026 规范）"""
        with self._lock:
            if self._initialized:
                get_display_registry().unregister('dependency_manager', 'status')
                self._initialized = False
                os_log.log_with_const('info', LogMsg.PLUGIN_CLOSED, 
                                     plugin='DependencyManager')

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
            with self._lock:
                self._last_report = payload
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
            with self._lock:
                self._last_report = result.get('report') if isinstance(result, dict) else None
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

