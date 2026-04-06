"""
env_guard - 环境守卫插件

功能：
    - 监控错误流并自动补救环境问题
    - 管理资源库和安装命令
    - 跟踪问题和尝试历史
    - 自动安装缺失的组件

2026 M03 规范：
    - __init__ 接受 node 和 **kwargs
    - get_required_config() 返回完整配置
    - auto_load() 初始化资源和启动工作线程
    - close() 清理资源
    - 所有操作线程安全
"""
import argparse
import json
import os
import queue
import shlex
import subprocess
import threading
import time
from copy import deepcopy
from pathlib import Path

from opensynaptic.utils import (
    os_log,
    LogMsg,
    EnvironmentMissingError,
)
from opensynaptic.services.display_api import DisplayProvider, get_display_registry


class EnvGuardDisplayProvider(DisplayProvider):
    """Display env_guard state with compact issue/attempt summary."""

    def __init__(self, plugin_ref):
        super().__init__(plugin_name='env_guard', section_id='status', display_name='Environment Guard Status')
        self.category = 'plugin'
        self.priority = 64
        self.refresh_interval_s = 4.0
        self._plugin = plugin_ref

    def extract_data(self, node=None, **kwargs):
        _ = node, kwargs
        plugin = self._plugin
        payload = plugin._status_payload()
        issues = payload.get('issues', []) if isinstance(payload.get('issues', []), list) else []
        attempts = payload.get('attempts', []) if isinstance(payload.get('attempts', []), list) else []
        return {
            'initialized': bool(getattr(plugin, '_initialized', False)),
            'auto_install': bool((getattr(plugin, 'config', {}) or {}).get('auto_install', False)),
            'issues_total': int(payload.get('issues_total', len(issues)) or 0),
            'attempts_total': int(payload.get('attempts_total', len(attempts)) or 0),
            'latest_issue': issues[-1] if issues else None,
            'latest_attempt': attempts[-1] if attempts else None,
            'resource_summary': payload.get('resource_summary', {}),
        }


class EnvironmentGuardService:
    """监视错误流并自动修复环境问题
    
    线程安全：是（使用 self._lock）
    Display Providers：env_guard:status
    """

    DEFAULT_RESOURCE_LIBRARY = {
        'resources': {
            'native_library': {
                'os_base62': {
                    'urls': [
                        'https://learn.microsoft.com/cpp/build/building-on-the-command-line',
                    ],
                    'commands': [
                        'python -u src/opensynaptic/utils/c/build_native.py',
                    ],
                },
            },
            'compiler': {
                'toolchain': {
                    'urls': [
                        'https://visualstudio.microsoft.com/visual-cpp-build-tools/',
                        'https://www.mingw-w64.org/',
                        'https://clang.llvm.org/',
                    ],
                    'commands': [
                        'winget install --id LLVM.LLVM -e --accept-package-agreements --accept-source-agreements',
                    ],
                },
            },
        },
    }

    def __init__(self, node=None, **kwargs):
        """初始化环境守卫插件（按 2026 规范）
        
        参数：
            node: OpenSynaptic 节点实例
            **kwargs: 配置字典
        """
        self.node = node
        self.config = kwargs or {}
        self._lock = threading.RLock()
        
        self._worker_thread = None
        self._stop_event = threading.Event()
        self._install_queue = queue.Queue()
        self._issues = []
        self._attempts = []
        self._initialized = False
        
        self._base_dir = Path(getattr(node, 'base_dir', Path(__file__).resolve().parents[4]))
        
        # 如果从 kwargs 没有获得配置，尝试从 node.config 获得
        if not self.config and node:
            try:
                resources = (getattr(node, 'config', {}) or {}).get('RESOURCES', {})
                self.config = (resources.get('service_plugins', {}) or {}).get('env_guard', {}) or {}
            except Exception:
                pass
        
        self._load_state_from_status_json()
        
        os_log.log_with_const('info', LogMsg.PLUGIN_INIT, 
                             plugin='EnvironmentGuard')

    @staticmethod
    def get_required_config():
        """返回默认配置（按 2026 规范）"""
        return {
            'enabled': True,
            'mode': 'manual',
            'auto_start': True,
            'auto_install': False,
            'max_history': 100,
            'install_commands': [],
            'resource_library_json_path': 'data/env_guard/resources.json',
            'status_json_path': 'data/env_guard/status.json',
        }

    def auto_load(self, config=None):
        """自动加载钩子（按 2026 规范）"""
        if config:
            self.config = config
        
        if not self.config.get('enabled', True):
            return self
        
        try:
            with self._lock:
                self.ensure_resource_library()
                os_log.add_error_listener(self._on_error)
                
                auto_start = bool(self.config.get('auto_start', True))
                if auto_start:
                    self.start()
                
                self._initialized = True
                reg = get_display_registry()
                reg.unregister('env_guard', 'status')
                reg.register(EnvGuardDisplayProvider(self))
                os_log.log_with_const('info', LogMsg.PLUGIN_READY, 
                                     plugin='EnvironmentGuard')
        except Exception as exc:
            os_log.err('ENV_GUARD', 'LOAD_FAILED', exc, {})
            self._initialized = False
        
        return self

    def close(self):
        """清理资源（按 2026 规范）"""
        with self._lock:
            if self._initialized:
                try:
                    self._stop_event.set()
                    os_log.remove_error_listener(self._on_error)
                    self._write_status_json()
                    get_display_registry().unregister('env_guard', 'status')
                    
                    self._initialized = False
                    os_log.log_with_const('info', LogMsg.PLUGIN_CLOSED, 
                                         plugin='EnvironmentGuard')
                except Exception as exc:
                    os_log.err('ENV_GUARD', 'CLOSE_FAILED', exc, {})

    def _resolve_path(self, config_key, default_rel_path):
        raw = self.config.get(config_key)
        path = Path(str(raw or default_rel_path))
        if not path.is_absolute():
            path = self._base_dir / path
        return path

    def _resolve_status_json_path(self):
        return self._resolve_path('status_json_path', 'data/env_guard/status.json')

    def _resolve_resource_library_json_path(self):
        return self._resolve_path('resource_library_json_path', 'data/env_guard/resources.json')

    def _read_json_file(self, path):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return {}

    def _write_json_file(self, path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')

    def ensure_resource_library(self, force_reset=False):
        target = self._resolve_resource_library_json_path()
        try:
            if force_reset or not target.exists():
                self._write_json_file(target, deepcopy(self.DEFAULT_RESOURCE_LIBRARY))
                return target
            parsed = self._read_json_file(target)
            if not isinstance(parsed, dict) or not isinstance(parsed.get('resources'), dict):
                self._write_json_file(target, deepcopy(self.DEFAULT_RESOURCE_LIBRARY))
        except Exception as exc:
            os_log.err('ENV_GUARD', 'WRITE_RESOURCE_JSON', exc, {'path': str(target)})
        return target

    def _write_status_json(self):
        payload = self._status_payload()
        target = self._resolve_status_json_path()
        try:
            self._write_json_file(target, payload)
        except Exception as exc:
            os_log.err('ENV_GUARD', 'WRITE_STATUS_JSON', exc, {'path': str(target)})

    def _read_resource_library(self):
        target = self.ensure_resource_library()
        parsed = self._read_json_file(target)
        if not isinstance(parsed, dict):
            return deepcopy(self.DEFAULT_RESOURCE_LIBRARY)
        if not isinstance(parsed.get('resources'), dict):
            return deepcopy(self.DEFAULT_RESOURCE_LIBRARY)
        return parsed

    def _load_state_from_status_json(self):
        target = self._resolve_status_json_path()
        parsed = self._read_json_file(target)
        if not isinstance(parsed, dict):
            return
        issues = parsed.get('issues')
        attempts = parsed.get('attempts')
        with self._lock:
            if isinstance(issues, list):
                self._issues = list(issues)
            if isinstance(attempts, list):
                self._attempts = list(attempts)

    def _resolve_resource_entry(self, missing_kind, resource):
        lib = self._read_resource_library().get('resources', {})
        by_kind = lib.get(str(missing_kind or '').strip(), {})
        if not isinstance(by_kind, dict):
            return {}
        for key in (str(resource or '').strip(), 'toolchain', '*', 'default'):
            if key and isinstance(by_kind.get(key), dict):
                return by_kind.get(key)
        return {}

    def _on_error(self, event):
        exc = event.get('error')
        payload = event.get('payload', {})
        if not isinstance(exc, EnvironmentMissingError):
            return
        issue = {
            'ts': round(time.time(), 3),
            'eid': payload.get('eid'),
            'mid': payload.get('mid'),
            'category': payload.get('category'),
            'error_type': payload.get('error_type'),
            'environment': exc.as_dict(),
        }
        with self._lock:
            self._issues.append(issue)
            max_history = int(self.config.get('max_history', 100))
            if len(self._issues) > max_history:
                self._issues = self._issues[-max_history:]
        if bool(self.config.get('auto_install', False)):
            self._install_queue.put(issue)
        self._write_status_json()

    def _install_worker(self):
        while not self._stop_event.is_set():
            try:
                issue = self._install_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            self._attempt_install(issue)

    def _attempt_install(self, issue):
        env_data = (issue or {}).get('environment', {})
        resource_entry = self._resolve_resource_entry(env_data.get('missing_kind'), env_data.get('resource'))
        commands = list(self.config.get('install_commands') or [])
        commands.extend(env_data.get('install_commands') or [])
        commands.extend(resource_entry.get('commands') or [])
        dedup_commands = []
        for cmd in commands:
            text = str(cmd).strip()
            if text and text not in dedup_commands:
                dedup_commands.append(text)

        urls = []
        for url in list(env_data.get('install_urls') or []) + list(resource_entry.get('urls') or []):
            text = str(url).strip()
            if text and text not in urls:
                urls.append(text)

        if not dedup_commands:
            self._record_attempt({'ok': False, 'reason': 'no-install-commands', 'suggested_urls': urls, 'issue': issue})
            return

        for cmd in dedup_commands:
            res = self._run_shell_command(str(cmd))
            res['issue'] = issue
            res['suggested_urls'] = urls
            self._record_attempt(res)
            if res.get('ok'):
                return

    @staticmethod
    def _run_shell_command(command):
        try:
            args = shlex.split(str(command), posix=(os.name != 'nt'))
            proc = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=180)
            return {
                'ok': proc.returncode == 0,
                'command': command,
                'return_code': proc.returncode,
                'stdout': (proc.stdout or '').strip(),
                'stderr': (proc.stderr or '').strip(),
                'ts': round(time.time(), 3),
            }
        except Exception as exc:
            return {
                'ok': False,
                'command': command,
                'return_code': None,
                'stdout': '',
                'stderr': str(exc),
                'ts': round(time.time(), 3),
            }

    def _record_attempt(self, attempt):
        with self._lock:
            self._attempts.append(attempt)
            max_history = int(self.config.get('max_history', 100))
            if len(self._attempts) > max_history:
                self._attempts = self._attempts[-max_history:]
        self._write_status_json()

    def _status_payload(self):
        status_json_path = str(self._resolve_status_json_path())
        resources_payload = self._read_resource_library()
        resource_map = resources_payload.get('resources', {}) if isinstance(resources_payload, dict) else {}
        resource_entries = 0
        resource_kinds = []
        for kind, mapping in (resource_map or {}).items():
            resource_kinds.append(kind)
            if isinstance(mapping, dict):
                resource_entries += len(mapping)
        with self._lock:
            issues = list(self._issues)
            attempts = list(self._attempts)
        return {
            'ok': True,
            'service': 'env_guard',
            'auto_install': bool(self.config.get('auto_install', False)),
            'status_json_path': status_json_path,
            'resource_library_json_path': str(self._resolve_resource_library_json_path()),
            'resource_summary': {
                'kinds': sorted(resource_kinds),
                'entries_total': resource_entries,
            },
            'issues_total': len(issues),
            'attempts_total': len(attempts),
            'issues': issues,
            'attempts': attempts,
        }

    def get_cli_commands(self):
        def _status(argv):
            _ = argv
            print(json.dumps(self._status_payload(), indent=2, ensure_ascii=False))
            return 0

        def _start(argv):
            _ = argv
            self.start()
            print(json.dumps({'ok': True, 'service': 'env_guard', 'status': 'started'}, ensure_ascii=False))
            return 0

        def _stop(argv):
            _ = argv
            self.close()
            print(json.dumps({'ok': True, 'service': 'env_guard', 'status': 'stopped'}, ensure_ascii=False))
            return 0

        def _set(argv):
            p = argparse.ArgumentParser(prog='env_guard set')
            p.add_argument('--auto-install', choices=['true', 'false'], required=False)
            ns = p.parse_args(argv)
            if ns.auto_install is not None:
                self.config['auto_install'] = (ns.auto_install == 'true')
            print(json.dumps({'ok': True, 'config': {'auto_install': bool(self.config.get('auto_install', False))}}, ensure_ascii=False))
            return 0

        def _resource_show(argv):
            _ = argv
            path = self.ensure_resource_library()
            payload = self._read_json_file(path)
            print(json.dumps({'ok': True, 'path': str(path), 'resources': payload.get('resources', {})}, indent=2, ensure_ascii=False))
            return 0

        def _resource_init(argv):
            _ = argv
            path = self.ensure_resource_library(force_reset=True)
            print(json.dumps({'ok': True, 'path': str(path), 'status': 'initialized'}, ensure_ascii=False))
            return 0

        return {
            'status': _status,
            'start': _start,
            'stop': _stop,
            'set': _set,
            'resource-show': _resource_show,
            'resource-init': _resource_init,
        }

    def start(self):
        """启动环境守卫工作线程"""
        self.ensure_resource_library()
        if self._worker_thread is None or not self._worker_thread.is_alive():
            self._stop_event.clear()
            self._worker_thread = threading.Thread(
                target=self._install_worker, 
                daemon=True, 
                name='os-env-guard-worker'
            )
            self._worker_thread.start()
        self._write_status_json()
