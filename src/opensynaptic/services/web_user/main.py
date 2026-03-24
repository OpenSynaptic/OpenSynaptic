import json
import io
import re
import shlex
import threading
import time
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from opensynaptic.utils import os_log


def _dotpath_get(payload, keypath):
    if not keypath:
        return payload
    current = payload
    for key in str(keypath).split('.'):
        if not isinstance(current, dict) or key not in current:
            raise KeyError(keypath)
        current = current[key]
    return current


def _dotpath_set(payload, keypath, value):
    current = payload
    keys = [k for k in str(keypath).split('.') if k]
    if not keys:
        raise KeyError('key is required')
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def _cast_value(raw, value_type):
    if value_type == 'int':
        return int(raw)
    if value_type == 'float':
        return float(raw)
    if value_type == 'bool':
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() not in ('0', 'false', 'no', 'off', '')
    if value_type == 'json':
        if isinstance(raw, str):
            return json.loads(raw)
        return raw
    return str(raw)


class WebUserService:
    """HTTP plugin that exposes user APIs plus node management endpoints."""

    DEFAULT_WRITE_PREFIXES = [
        'RESOURCES.service_plugins',
        'RESOURCES.application_status',
        'RESOURCES.transport_status',
        'RESOURCES.physical_status',
        'RESOURCES.application_config',
        'RESOURCES.transport_config',
        'RESOURCES.physical_config',
        'engine_settings',
    ]

    FIELD_ANNOTATIONS = {
        'engine_settings.core_backend': 'Active core backend plugin.',
        'engine_settings.precision': 'Base62 decimal precision for values.',
        'engine_settings.active_standardization': 'Enable UCUM standardization stage.',
        'engine_settings.active_compression': 'Enable Base62 compression stage.',
        'engine_settings.active_collapse': 'Enable binary collapse stage.',
        'security_settings.id_lease.base_lease_seconds': 'Default offline lease duration in seconds.',
        'security_settings.id_lease.high_rate_threshold_per_hour': 'High-rate threshold for adaptive lease.',
        'security_settings.id_lease.ultra_rate_threshold_per_hour': 'Ultra-rate threshold for force-release mode.',
        'RESOURCES.service_plugins.web_user.ui_enabled': 'Enable web dashboard page on route /.',
        'RESOURCES.service_plugins.web_user.ui_theme': 'Dashboard visual theme.',
        'RESOURCES.service_plugins.web_user.ui_refresh_seconds': 'Auto-refresh interval for dashboard widgets.',
        'RESOURCES.service_plugins.web_user.read_only': 'Block all write operations from web APIs.',
        'RESOURCES.service_plugins.web_user.auth_enabled': 'Require X-Admin-Token for management APIs.',
        'RESOURCES.transport_status.udp': 'Enable UDP transport driver.',
        'RESOURCES.transport_status.tcp': 'Enable TCP transport driver.',
        'RESOURCES.physical_status.uart': 'Enable UART physical driver.',
        'RESOURCES.application_status.mqtt': 'Enable MQTT application driver.',
    }

    def __init__(self, node=None):
        self.node = node
        self._base_dir = Path(getattr(node, 'base_dir', Path(__file__).resolve().parents[4]))
        self._data_file = self._base_dir / 'data' / 'web_users.json'
        self._lock = threading.RLock()
        self._server = None
        self._thread = None
        self._started_at = None
        self._users = {'users': []}
        self._settings = self._resolve_settings()
        self._cli_jobs_lock = threading.RLock()
        self._cli_jobs = {}
        self._cli_job_seq = 0
        self._latest_run_stats = {}
        self._latest_perf_stats = {}
        self._load_users()

    @staticmethod
    def get_required_config():
        return {
            'enabled': True,
            'mode': 'manual',
            'host': '127.0.0.1',
            'port': 8765,
            'auto_start': False,
            'management_enabled': True,
            'auth_enabled': False,
            'admin_token': '',
            'read_only': False,
            'writable_config_prefixes': list(WebUserService.DEFAULT_WRITE_PREFIXES),
            'expose_sections': ['identity', 'transport', 'plugins', 'pipeline', 'config', 'users'],
            'ui_enabled': True,
            'ui_theme': 'router-dark',
            'ui_layout': 'sidebar',
            'ui_refresh_seconds': 3,
            'ui_compact': False,
        }

    def _resolve_settings(self):
        cfg = {}
        if self.node and isinstance(getattr(self.node, 'config', None), dict):
            cfg = self.node.config.get('RESOURCES', {}).get('service_plugins', {}).get('web_user', {})
        defaults = self.get_required_config()
        out = dict(defaults)
        if isinstance(cfg, dict):
            out.update(cfg)
        return out

    def _load_users(self):
        with self._lock:
            try:
                if self._data_file.exists():
                    payload = json.loads(self._data_file.read_text(encoding='utf-8'))
                    users = payload.get('users', []) if isinstance(payload, dict) else []
                    if isinstance(users, list):
                        self._users = {'users': users}
                        return
            except Exception as exc:
                os_log.err('WEB_USER', 'LOAD', exc, {'path': str(self._data_file)})
            self._users = {'users': []}

    def _refresh_settings(self):
        self._settings = self._resolve_settings()
        return self._settings

    def _is_management_enabled(self):
        return bool(self._settings.get('management_enabled', True))

    def _is_read_only(self):
        return bool(self._settings.get('read_only', False))

    def _is_auth_enabled(self):
        return bool(self._settings.get('auth_enabled', False))

    def _allowed_write_prefixes(self):
        raw = self._settings.get('writable_config_prefixes', self.DEFAULT_WRITE_PREFIXES)
        if not isinstance(raw, list):
            return list(self.DEFAULT_WRITE_PREFIXES)
        return [str(item).strip() for item in raw if str(item).strip()]

    def _is_key_writable(self, key):
        normalized = str(key or '').strip()
        if not normalized:
            return False
        for prefix in self._allowed_write_prefixes():
            if normalized == prefix or normalized.startswith(prefix + '.'):
                return True
        return False

    def _authorize_request(self, headers, write=False, management=False):
        if management and (not self._is_management_enabled()):
            return False, 403, 'management api disabled'
        if write and self._is_read_only():
            return False, 403, 'read-only mode is active'
        if self._is_auth_enabled():
            expected = str(self._settings.get('admin_token', '') or '').strip()
            provided = str((headers or {}).get('X-Admin-Token', '') or '').strip()
            if not expected:
                return False, 503, 'auth_enabled=true but admin_token is empty'
            if provided != expected:
                return False, 401, 'admin token required'
        return True, 200, None

    def _save_users(self):
        with self._lock:
            self._data_file.parent.mkdir(parents=True, exist_ok=True)
            self._data_file.write_text(json.dumps(self._users, indent=2, ensure_ascii=False), encoding='utf-8')

    def _config_ref(self):
        if self.node and isinstance(getattr(self.node, 'config', None), dict):
            return self.node.config
        return {}

    def _service_snapshot(self):
        manager = getattr(self.node, 'service_manager', None)
        if manager and hasattr(manager, 'snapshot'):
            return manager.snapshot()
        return {'mount_index': [], 'runtime_index': {}, 'config_index': {}}

    def _transport_snapshot(self):
        cfg = self._config_ref()
        res = cfg.get('RESOURCES', {}) if isinstance(cfg, dict) else {}
        return {
            'active_transporters': sorted(list(getattr(self.node, 'active_transporters', {}).keys())),
            'application_status': res.get('application_status', {}),
            'transport_status': res.get('transport_status', {}),
            'physical_status': res.get('physical_status', {}),
            'transporters_status': res.get('transporters_status', {}),
        }

    def _pipeline_snapshot(self):
        cfg = self._config_ref()
        settings = cfg.get('engine_settings', {}) if isinstance(cfg, dict) else {}
        standardizer = getattr(self.node, 'standardizer', None)
        engine = getattr(self.node, 'engine', None)
        fusion = getattr(self.node, 'fusion', None)
        ram_cache = getattr(fusion, '_RAM_CACHE', {}) if fusion is not None else {}
        return {
            'settings': settings,
            'standardizer_cache_entries': len(getattr(standardizer, 'registry', {}) or {}),
            'engine_rev_unit_entries': len(getattr(engine, 'REV_UNIT', {}) or {}),
            'fusion_cached_aids': list((ram_cache or {}).keys()),
        }

    def _resolve_sections(self, requested=None):
        allowed_raw = self._settings.get('expose_sections', ['identity', 'plugins', 'transport', 'pipeline', 'users', 'config'])
        allowed = [str(item).strip().lower() for item in (allowed_raw or []) if str(item).strip()]
        if not allowed:
            allowed = ['identity']
        if requested is None:
            return allowed
        wanted = [str(item).strip().lower() for item in (requested or []) if str(item).strip()]
        chosen = [name for name in wanted if name in allowed]
        return chosen or allowed

    def _ui_config_payload(self):
        self._refresh_settings()
        return {
            'ui_enabled': bool(self._settings.get('ui_enabled', True)),
            'ui_theme': str(self._settings.get('ui_theme', 'router-dark')),
            'ui_layout': str(self._settings.get('ui_layout', 'sidebar')),
            'ui_refresh_seconds': max(1, int(self._settings.get('ui_refresh_seconds', 3) or 3)),
            'ui_compact': bool(self._settings.get('ui_compact', False)),
            'expose_sections': self._resolve_sections(None),
        }

    def _update_ui_config(self, payload):
        if not isinstance(payload, dict):
            return False, {'error': 'payload must be object'}
        allowed_keys = {'ui_enabled', 'ui_theme', 'ui_layout', 'ui_refresh_seconds', 'ui_compact', 'expose_sections'}
        cleaned = {}
        for key, value in payload.items():
            if key not in allowed_keys:
                continue
            if key in ('ui_enabled', 'ui_compact'):
                cleaned[key] = bool(value)
            elif key == 'ui_refresh_seconds':
                cleaned[key] = max(1, int(value or 1))
            elif key == 'expose_sections':
                if isinstance(value, list):
                    cleaned[key] = [str(item).strip().lower() for item in value if str(item).strip()]
            else:
                cleaned[key] = str(value)
        cfg = self._config_ref()
        plugin_cfg = (((cfg.setdefault('RESOURCES', {})).setdefault('service_plugins', {})).setdefault('web_user', {}))
        plugin_cfg.update(cleaned)
        saver = getattr(self.node, '_save_config', None)
        if callable(saver):
            saver()
        return True, {'ok': True, 'ui': self._ui_config_payload()}

    def build_dashboard(self, sections=None):
        self._refresh_settings()
        cfg = self._config_ref()
        service_cfg = (((cfg.get('RESOURCES', {}) or {}).get('service_plugins', {}) or {}).get('web_user', {}) or {})
        full_sections = {
            'identity': {
                'device_id': getattr(self.node, 'device_id', 'UNKNOWN'),
                'assigned_id': getattr(self.node, 'assigned_id', None),
                'core_backend': ((cfg.get('engine_settings', {}) or {}).get('core_backend', 'pycore') if isinstance(cfg, dict) else 'pycore'),
            },
            'plugins': self._service_snapshot(),
            'transport': self._transport_snapshot(),
            'pipeline': self._pipeline_snapshot(),
            'users': self.list_users(),
            'config': {'engine_settings': cfg.get('engine_settings', {}), 'security_settings': cfg.get('security_settings', {})},
        }
        selected_sections = self._resolve_sections(sections)
        payload = {
            'service': {
                'name': 'web_user',
                'running': self._server is not None,
                'uptime_s': round(time.time() - self._started_at, 3) if self._started_at else 0.0,
                'host': service_cfg.get('host', self._settings.get('host', '127.0.0.1')),
                'port': int(service_cfg.get('port', self._settings.get('port', 8765))),
                'read_only': self._is_read_only(),
                'management_enabled': self._is_management_enabled(),
                'auth_enabled': self._is_auth_enabled(),
            },
            'available_sections': self._resolve_sections(None),
            'sections': selected_sections,
            'overview_metrics': self.get_overview_metrics(),
            'timestamp': int(time.time()),
        }
        for name in selected_sections:
            payload[name] = full_sections.get(name, {})
        return payload

    def _config_get_payload(self, key=None):
        cfg = self._config_ref()
        if not key:
            return {'ok': True, 'config': cfg}
        return {'ok': True, 'key': key, 'value': _dotpath_get(cfg, key)}

    def _config_set_payload(self, key, value, value_type='json'):
        if not self._is_key_writable(key):
            return False, {'error': 'write blocked by writable_config_prefixes', 'key': key}
        cfg = self._config_ref()
        typed = _cast_value(value, value_type)
        old_val = None
        try:
            old_val = _dotpath_get(cfg, key)
        except Exception:
            old_val = None
        _dotpath_set(cfg, key, typed)
        saver = getattr(self.node, '_save_config', None)
        if callable(saver):
            saver()
        return True, {'ok': True, 'key': key, 'old': old_val, 'new': typed}

    @staticmethod
    def _friendly_label(path):
        leaf = str(path or '').split('.')[-1]
        return leaf.replace('_', ' ').strip().title() or str(path)

    @staticmethod
    def _infer_value_type(value):
        if isinstance(value, bool):
            return 'bool'
        if isinstance(value, int) and (not isinstance(value, bool)):
            return 'int'
        if isinstance(value, float):
            return 'float'
        if isinstance(value, str):
            return 'str'
        return 'json'

    def _field_annotation(self, path):
        exact = self.FIELD_ANNOTATIONS.get(path)
        if exact:
            return exact
        leaf = str(path or '').split('.')[-1]
        if leaf.endswith('enabled'):
            return 'Toggle switch for this feature.'
        if leaf.endswith('port'):
            return 'Network or device port value.'
        if leaf.endswith('host'):
            return 'Target hostname or bind address.'
        if leaf.endswith('seconds'):
            return 'Duration in seconds.'
        return 'Auto-generated from current config value type.'

    def _flatten_option_fields(self, path, value, fields):
        if isinstance(value, dict):
            for key in sorted(value.keys()):
                next_path = '{}.{}'.format(path, key) if path else str(key)
                self._flatten_option_fields(next_path, value.get(key), fields)
            return
        field_type = self._infer_value_type(value)
        fields.append({
            'key': path,
            'label': self._friendly_label(path),
            'description': self._field_annotation(path),
            'type': field_type,
            'value': value,
            'writable': self._is_key_writable(path),
            'choices': [True, False] if field_type == 'bool' else None,
        })

    def _category_title(self, prefix):
        titles = {
            'RESOURCES.service_plugins': 'Service Plugins',
            'RESOURCES.application_status': 'Application Drivers',
            'RESOURCES.transport_status': 'Transport Drivers',
            'RESOURCES.physical_status': 'Physical Drivers',
            'RESOURCES.application_config': 'Application Config',
            'RESOURCES.transport_config': 'Transport Config',
            'RESOURCES.physical_config': 'Physical Config',
            'engine_settings': 'Engine Settings',
            'security_settings.id_lease': 'ID Lease Policy',
        }
        return titles.get(prefix, self._friendly_label(prefix))

    def build_option_schema(self, only_writable=False):
        cfg = self._config_ref()
        prefixes = [
            'RESOURCES.service_plugins.web_user',
            'RESOURCES.application_status',
            'RESOURCES.transport_status',
            'RESOURCES.physical_status',
            'engine_settings',
            'security_settings.id_lease',
        ]
        categories = []
        for prefix in prefixes:
            try:
                value = _dotpath_get(cfg, prefix)
            except Exception:
                continue
            fields = []
            self._flatten_option_fields(prefix, value, fields)
            if only_writable:
                fields = [item for item in fields if bool(item.get('writable'))]
            if not fields:
                continue
            categories.append({
                'id': prefix,
                'title': self._category_title(prefix),
                'count': len(fields),
                'fields': fields,
            })
        return {
            'generated_at': int(time.time()),
            'categories': categories,
            'writable_prefixes': self._allowed_write_prefixes(),
        }

    def apply_option_updates(self, updates):
        if not isinstance(updates, list):
            return False, {'error': 'updates must be a list'}
        changed = []
        failed = []
        for item in updates:
            if not isinstance(item, dict):
                failed.append({'item': item, 'error': 'invalid update object'})
                continue
            key = str(item.get('key', '') or '').strip()
            value = item.get('value')
            value_type = str(item.get('value_type', '') or '').strip().lower()
            if not key:
                failed.append({'item': item, 'error': 'key is required'})
                continue
            if not value_type:
                current = None
                try:
                    current = _dotpath_get(self._config_ref(), key)
                except Exception:
                    current = value
                value_type = self._infer_value_type(current)
            ok, payload = self._config_set_payload(key=key, value=value, value_type=value_type)
            if ok:
                changed.append({'key': key, 'new': payload.get('new')})
            else:
                failed.append({'key': key, 'error': payload.get('error', 'update failed')})
        return True, {'ok': len(failed) == 0, 'changed': changed, 'failed': failed}

    def _ingest_cli_output_line(self, line):
        text = str(line or '').strip()
        if not text:
            return
        try:
            payload = json.loads(text)
            if isinstance(payload, dict) and isinstance(payload.get('run_stats'), dict):
                self._latest_run_stats = dict(payload.get('run_stats', {}))
                return
        except Exception:
            pass

        if 'Performance stats' not in text:
            return
        pattern = (
            r"recv=(?P<recv>\d+)\s+ok=(?P<ok>\d+)\s+fail=(?P<fail>\d+)\s+drop=(?P<drop>\d+)"
            r"\s+backlog=(?P<backlog_cur>\d+)/(?:\s*)?(?P<backlog_max>\d+)"
            r"\s+avg=(?P<avg>[0-9.]+)ms\s+max=(?P<max>[0-9.]+)ms"
            r"\s+pps\(in/out\)=(?P<pps_in>[0-9.]+)/(?P<pps_out>[0-9.]+)"
        )
        m = re.search(pattern, text)
        if not m:
            return
        self._latest_perf_stats = {
            'recv': int(m.group('recv')),
            'ok': int(m.group('ok')),
            'fail': int(m.group('fail')),
            'drop': int(m.group('drop')),
            'backlog_current': int(m.group('backlog_cur')),
            'backlog_max': int(m.group('backlog_max')),
            'avg_ms': float(m.group('avg')),
            'max_ms': float(m.group('max')),
            'pps_in': float(m.group('pps_in')),
            'pps_out': float(m.group('pps_out')),
        }

    @staticmethod
    def _coerce_cli_tokens(command_line):
        line = str(command_line or '').strip()
        if not line:
            return []
        return shlex.split(line)

    def _run_opensynaptic_cli_tokens(self, tokens):
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        rc = 1
        try:
            from opensynaptic.CLI.app import main as os_cli_main
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                try:
                    maybe = os_cli_main(tokens)
                    rc = int(maybe or 0)
                except SystemExit as exc:
                    rc = int(exc.code) if isinstance(exc.code, int) else 1
        except Exception as exc:
            err_buf.write(str(exc))
            rc = 1
        stdout_text = out_buf.getvalue()
        stderr_text = err_buf.getvalue()
        for ln in stdout_text.splitlines():
            self._ingest_cli_output_line(ln)
        for ln in stderr_text.splitlines():
            self._ingest_cli_output_line(ln)
        return rc, stdout_text, stderr_text

    def _next_cli_job_id(self):
        with self._cli_jobs_lock:
            self._cli_job_seq += 1
            return str(self._cli_job_seq)

    @staticmethod
    def _clip_text(text, limit):
        raw = str(text or '')
        cap = max(0, int(limit or 0))
        if cap <= 0 or len(raw) <= cap:
            return raw, False
        return raw[:cap], True

    def _job_snapshot(self, job, include_output=False, output_limit=120000):
        base = {
            'id': job.get('id'),
            'command': job.get('command'),
            'status': job.get('status'),
            'created_at': job.get('created_at'),
            'started_at': job.get('started_at'),
            'finished_at': job.get('finished_at'),
            'exit_code': job.get('exit_code'),
            'error': job.get('error'),
            'stdout_len': len(str(job.get('stdout', '') or '')),
            'stderr_len': len(str(job.get('stderr', '') or '')),
        }
        if include_output:
            out_clip, out_trunc = self._clip_text(job.get('stdout', ''), output_limit)
            err_clip, err_trunc = self._clip_text(job.get('stderr', ''), output_limit)
            base['stdout'] = out_clip
            base['stderr'] = err_clip
            base['stdout_truncated'] = bool(out_trunc)
            base['stderr_truncated'] = bool(err_trunc)
        else:
            out_preview, _ = self._clip_text(job.get('stdout', ''), 800)
            err_preview, _ = self._clip_text(job.get('stderr', ''), 400)
            base['stdout_preview'] = out_preview
            base['stderr_preview'] = err_preview
        return base

    def submit_os_cli_job(self, command, background=True):
        tokens = self._coerce_cli_tokens(command)
        if not tokens:
            return False, {'error': 'empty command'}
        job_id = self._next_cli_job_id()
        job = {
            'id': job_id,
            'command': ' '.join(tokens),
            'status': 'queued',
            'created_at': int(time.time()),
            'started_at': None,
            'finished_at': None,
            'exit_code': None,
            'stdout': '',
            'stderr': '',
            'error': None,
        }
        with self._cli_jobs_lock:
            self._cli_jobs[job_id] = job

        def _runner():
            with self._cli_jobs_lock:
                job['status'] = 'running'
                job['started_at'] = int(time.time())
            try:
                rc, out, err = self._run_opensynaptic_cli_tokens(tokens)
                with self._cli_jobs_lock:
                    job['exit_code'] = int(rc)
                    job['stdout'] = out
                    job['stderr'] = err
                    job['status'] = 'succeeded' if rc == 0 else 'failed'
            except Exception as exc:
                with self._cli_jobs_lock:
                    job['status'] = 'failed'
                    job['error'] = str(exc)
            finally:
                with self._cli_jobs_lock:
                    job['finished_at'] = int(time.time())

        if background:
            threading.Thread(target=_runner, name='os-web-cli-job-{}'.format(job_id), daemon=True).start()
            return True, {'ok': True, 'job': self._job_snapshot(job, include_output=False)}
        _runner()
        return True, {'ok': True, 'job': self._job_snapshot(job, include_output=True, output_limit=120000)}

    def get_os_cli_job(self, job_id, include_output=False, output_limit=120000):
        with self._cli_jobs_lock:
            job = self._cli_jobs.get(str(job_id))
            return self._job_snapshot(job, include_output=include_output, output_limit=output_limit) if isinstance(job, dict) else None

    def list_os_cli_jobs(self, limit=20, include_output=False, output_limit=120000):
        with self._cli_jobs_lock:
            rows = sorted(self._cli_jobs.values(), key=lambda item: int(item.get('id', 0)), reverse=True)
            return [
                self._job_snapshot(item, include_output=include_output, output_limit=output_limit)
                for item in rows[:max(1, int(limit or 20))]
            ]

    def get_overview_metrics(self):
        run_stats = dict(self._latest_run_stats or {})
        perf_stats = dict(self._latest_perf_stats or {})
        return {
            'run_stats': {
                'status': run_stats.get('status', 'idle'),
                'uptime_s': int(run_stats.get('uptime_s', 0) or 0),
                'packets_processed': int(run_stats.get('packets_processed', 0) or 0),
                'avg_packet_latency_ms': float(run_stats.get('avg_packet_latency_ms', 0.0) or 0.0),
                'tick_errors': int(run_stats.get('tick_errors', 0) or 0),
            },
            'performance_stats': {
                'recv': int(perf_stats.get('recv', 0) or 0),
                'ok': int(perf_stats.get('ok', 0) or 0),
                'fail': int(perf_stats.get('fail', 0) or 0),
                'drop': int(perf_stats.get('drop', 0) or 0),
                'backlog_current': int(perf_stats.get('backlog_current', 0) or 0),
                'backlog_max': int(perf_stats.get('backlog_max', 0) or 0),
                'avg_ms': float(perf_stats.get('avg_ms', 0.0) or 0.0),
                'max_ms': float(perf_stats.get('max_ms', 0.0) or 0.0),
                'pps_in': float(perf_stats.get('pps_in', 0.0) or 0.0),
                'pps_out': float(perf_stats.get('pps_out', 0.0) or 0.0),
            },
            'jobs': {
                'total': len(self._cli_jobs),
                'recent': self.list_os_cli_jobs(limit=5),
            },
        }

    def build_overview_payload(self):
        cfg = self._config_ref()
        return {
            'service': {
                'running': self._server is not None,
                'uptime_s': round(time.time() - self._started_at, 3) if self._started_at else 0.0,
            },
            'identity': {
                'device_id': getattr(self.node, 'device_id', 'UNKNOWN'),
                'assigned_id': getattr(self.node, 'assigned_id', None),
                'core_backend': ((cfg.get('engine_settings', {}) or {}).get('core_backend', 'pycore') if isinstance(cfg, dict) else 'pycore'),
            },
            'overview_metrics': self.get_overview_metrics(),
            'timestamp': int(time.time()),
        }

    def _sync_legacy_transporters_status(self):
        cfg = self._config_ref()
        res = cfg.setdefault('RESOURCES', {})
        merged = {}
        merged.update(res.get('application_status', {}) if isinstance(res.get('application_status', {}), dict) else {})
        merged.update(res.get('transport_status', {}) if isinstance(res.get('transport_status', {}), dict) else {})
        merged.update(res.get('physical_status', {}) if isinstance(res.get('physical_status', {}), dict) else {})
        res['transporters_status'] = merged

    def _set_transport_enabled(self, medium, enabled):
        key = str(medium or '').strip().lower()
        if not key:
            return False, 'medium is required'
        cfg = self._config_ref()
        res = cfg.setdefault('RESOURCES', {})
        app = res.setdefault('application_status', {})
        transport = res.setdefault('transport_status', {})
        physical = res.setdefault('physical_status', {})
        if key in app:
            app[key] = bool(enabled)
        elif key in transport:
            transport[key] = bool(enabled)
        elif key in physical:
            physical[key] = bool(enabled)
        else:
            return False, 'unknown medium'
        self._sync_legacy_transporters_status()
        saver = getattr(self.node, '_save_config', None)
        if callable(saver):
            saver()
        return True, None

    def _reload_transport(self, medium):
        tm = getattr(self.node, 'transporter_manager', None)
        refresh = getattr(tm, 'refresh_protocol', None)
        if not callable(refresh):
            return False
        return bool(refresh(medium))

    def _run_plugin_action(self, plugin_name, action, sub_cmd='', args=None):
        if not self.node or not hasattr(self.node, 'service_manager'):
            return False, {'error': 'service manager unavailable'}
        from opensynaptic.services.plugin_registry import ensure_and_mount_plugin, normalize_plugin_name

        key = normalize_plugin_name(plugin_name)
        ensure_and_mount_plugin(self.node, key, load=True, mode='runtime')
        if action == 'load':
            return True, {'ok': True, 'plugin': key, 'action': 'load'}
        if action == 'start':
            svc = self.node.service_manager.get(key)
            if svc is None or not hasattr(svc, 'start'):
                return False, {'error': 'plugin has no start()', 'plugin': key}
            svc.start()
            return True, {'ok': True, 'plugin': key, 'action': 'start'}
        if action == 'stop':
            svc = self.node.service_manager.get(key)
            if svc is None or not hasattr(svc, 'stop'):
                return False, {'error': 'plugin has no stop()', 'plugin': key}
            svc.stop()
            return True, {'ok': True, 'plugin': key, 'action': 'stop'}
        if action == 'cmd':
            cmd = str(sub_cmd or '').strip()
            if not cmd:
                return False, {'error': 'sub_cmd is required for action=cmd', 'plugin': key}
            rc = self.node.service_manager.dispatch_plugin_cli(key, [cmd] + list(args or []))
            return rc == 0, {'ok': rc == 0, 'plugin': key, 'action': 'cmd', 'exit_code': int(rc)}
        return False, {'error': 'unknown action', 'action': action}

    @staticmethod
    def cli_help_table():
        return {
            'status': 'Show node status overview.',
            'pipeline-info': 'Show pipeline flags and cache stats.',
            'plugin-test --suite component': 'Run component suite and print report.',
            'plugin-test --suite stress --workers 8 --total 200': 'Run stress suite.',
            'config-get --key engine_settings.precision': 'Read one config dotted key.',
            'config-set --key engine_settings.precision --value 6 --type int': 'Write one config key.',
            'transport-status': 'Show application/transport/physical status maps.',
            'help --full': 'Show full OpenSynaptic CLI help.',
        }

    @staticmethod
    def _to_bool(value):
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ('1', 'true', 'yes', 'on', 'enable', 'enabled')

    def execute_control_cli(self, command_line):
        tokens = self._coerce_cli_tokens(command_line)
        if not tokens:
            return False, {'error': 'empty command'}
        rc, out, err = self._run_opensynaptic_cli_tokens(tokens)
        return rc == 0, {
            'ok': rc == 0,
            'command': ' '.join(tokens),
            'exit_code': int(rc),
            'stdout': out,
            'stderr': err,
        }

    def _find_user(self, username):
        for item in self._users.get('users', []):
            if str(item.get('username', '')).lower() == str(username).lower():
                return item
        return None

    def list_users(self):
        with self._lock:
            return list(self._users.get('users', []))

    def create_user(self, username, role='user', enabled=True):
        with self._lock:
            if self._find_user(username):
                return False, 'user already exists'
            now = int(time.time())
            self._users['users'].append({
                'username': str(username),
                'role': str(role or 'user'),
                'enabled': bool(enabled),
                'created_at': now,
                'updated_at': now,
            })
            self._save_users()
            return True, None

    def update_user(self, username, role=None, enabled=None):
        with self._lock:
            user = self._find_user(username)
            if not user:
                return False, 'user not found'
            if role is not None:
                user['role'] = str(role)
            if enabled is not None:
                user['enabled'] = bool(enabled)
            user['updated_at'] = int(time.time())
            self._save_users()
            return True, None

    def delete_user(self, username):
        with self._lock:
            users = self._users.get('users', [])
            before = len(users)
            users = [u for u in users if str(u.get('username', '')).lower() != str(username).lower()]
            if len(users) == before:
                return False, 'user not found'
            self._users['users'] = users
            self._save_users()
            return True, None

    def _json_response(self, handler, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
        handler.send_response(status_code)
        handler.send_header('Content-Type', 'application/json; charset=utf-8')
        handler.send_header('Content-Length', str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _html_response(self, handler, status_code, html_text):
        body = html_text.encode('utf-8')
        handler.send_response(status_code)
        handler.send_header('Content-Type', 'text/html; charset=utf-8')
        handler.send_header('Content-Length', str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _text_response(self, handler, status_code, text, content_type='text/plain; charset=utf-8'):
        body = str(text).encode('utf-8')
        handler.send_response(status_code)
        handler.send_header('Content-Type', content_type)
        handler.send_header('Content-Length', str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    @staticmethod
    def _runtime_js():
        # External runtime fallback for browsers/environments that block inline scripts.
        return r"""
(function () {
  function byId(id) { return document.getElementById(id); }
  function setText(id, v) { var el = byId(id); if (el) { el.textContent = String(v); } }
  function setBanner(state, msg) {
    var el = byId('connectionBanner');
    if (!el) { return; }
    el.className = 'conn-banner' + (state === 'ok' ? ' ok' : (state === 'bad' ? ' bad' : ''));
    el.textContent = msg;
  }
  function tokenHeader(xhr) {
    var tokenEl = byId('token');
    var token = tokenEl ? String(tokenEl.value || '').trim() : '';
    if (token) { xhr.setRequestHeader('X-Admin-Token', token); }
  }
  function req(method, path, body, cb) {
    var xhr = new XMLHttpRequest();
    xhr.open(method, path, true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    tokenHeader(xhr);
    xhr.onreadystatechange = function () {
      if (xhr.readyState !== 4) { return; }
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          var data = JSON.parse(xhr.responseText || '{}');
          setBanner('ok', 'Connected to web service.');
          cb(null, data);
          return;
        } catch (e) {
          setBanner('bad', 'Connected but invalid JSON response.');
          cb(e || new Error('invalid json'));
          return;
        }
      }
      setBanner('bad', 'Disconnected: HTTP ' + String(xhr.status) + ' (auto retrying)');
      cb(new Error('http ' + String(xhr.status)));
    };
    try {
      xhr.send(body ? JSON.stringify(body) : null);
    } catch (e) {
      setBanner('bad', 'Disconnected: network error (auto retrying)');
      cb(e || new Error('network error'));
    }
  }
  function renderOverview(payload) {
    var d = payload && payload.overview ? payload.overview : {};
    var idn = d.identity || {};
    var svc = d.service || {};
    var m = d.overview_metrics || {};
    var run = m.run_stats || {};
    var perf = m.performance_stats || {};
    var jobs = m.jobs || {};
    var dot = byId('runningDot');
    if (dot) { dot.classList.toggle('ok', !!svc.running); }
    setText('runningLabel', svc.running ? 'service running' : 'service stopped');
    setText('kpiDevice', idn.device_id || '-');
    setText('kpiAid', idn.assigned_id == null ? '-' : idn.assigned_id);
    setText('kpiCore', idn.core_backend || '-');
    setText('kpiUp', String(svc.uptime_s || 0) + ' s');
    setText('runStatus', run.status || 'idle');
    setText('runPackets', run.packets_processed || 0);
    setText('runLatency', run.avg_packet_latency_ms || 0.0);
    setText('runErrors', run.tick_errors || 0);
    setText('perfStatsView', JSON.stringify(perf, null, 2));
    setText('jobStatsView', JSON.stringify({total: jobs.total || 0, recent: jobs.recent || []}, null, 2));
  }
  function reloadAll() {
    req('GET', '/api/overview', null, function (err, payload) {
      if (err || !payload) {
        setText('perfStatsView', 'Failed to load overview.');
        return;
      }
      renderOverview(payload);
      req('GET', '/users', null, function (_e, usersPayload) {
        if (_e || !usersPayload) { return; }
        var rows = usersPayload.users || [];
        var html = '';
        for (var i = 0; i < rows.length; i++) {
          var u = rows[i] || {};
          var uname = String(u.username || '');
          var role = String(u.role || 'user');
          var checked = u.enabled ? 'checked' : '';
          html += '<tr>' +
            '<td>' + uname + '</td>' +
            '<td><input id="role-' + uname + '" value="' + role + '"></td>' +
            '<td><input id="on-' + uname + '" type="checkbox" ' + checked + '></td>' +
            '<td><button data-user-action="update" data-username="' + uname + '">Update</button> <button data-user-action="delete" data-username="' + uname + '">Delete</button></td>' +
            '</tr>';
        }
        var tb = byId('users');
        if (tb) { tb.innerHTML = html; }
      });
    });
  }
  function setCmd(text) {
    var el = byId('cmdLine');
    if (el) { el.value = String(text || ''); }
  }
  function runCommandLine() {
    var el = byId('cmdLine');
    var line = el ? String(el.value || '').trim() : '';
    if (!line) { return; }
    req('POST', '/api/oscli/execute', {command: line, background: true}, function (err, payload) {
      setText('cmdResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
    });
  }
  function loadCommandHelp() {
    req('POST', '/api/oscli/execute', {command: 'help --full', background: false}, function (err, payload) {
      setText('cmdResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
    });
  }
  function runPluginAction() {
    var plugin = byId('pluginName');
    var action = byId('pluginAction');
    var sub = byId('pluginSubCmd');
    var argsEl = byId('pluginArgs');
    var args = [];
    try { args = JSON.parse(String(argsEl && argsEl.value || '[]')); } catch (_e) { args = []; }
    req('POST', '/api/plugins', {
      plugin: plugin ? plugin.value : 'web_user',
      action: action ? action.value : 'load',
      sub_cmd: sub ? sub.value : '',
      args: args,
    }, function (err, payload) {
      setText('pluginResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
      reloadAll();
    });
  }
  function toggleTransport() {
    var medium = byId('medium');
    var state = byId('mediumState');
    req('POST', '/api/transport', {
      medium: medium ? medium.value : '',
      enabled: state ? String(state.value) === 'true' : true,
    }, function (err, payload) {
      setText('transportResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
      reloadAll();
    });
  }
  function reloadTransport() {
    var medium = byId('medium');
    req('POST', '/api/transport', {medium: medium ? medium.value : '', reload: true}, function (err, payload) {
      setText('transportResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
      reloadAll();
    });
  }
  function getConfig() {
    var key = byId('cfgKey');
    var path = '/api/config';
    if (key && String(key.value || '').trim()) {
      path += '?key=' + encodeURIComponent(String(key.value).trim());
    }
    req('GET', path, null, function (err, payload) {
      setText('configResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
    });
  }
  function setConfig() {
    var key = byId('cfgKey');
    var value = byId('cfgValue');
    var valueType = byId('cfgType');
    req('PUT', '/api/config', {
      key: key ? key.value : '',
      value: value ? value.value : '',
      value_type: valueType ? valueType.value : 'json',
    }, function (err, payload) {
      setText('configResult', JSON.stringify(payload || {ok: false, error: String(err || 'request failed')}, null, 2));
      reloadAll();
    });
  }
  function addUser() {
    var u = byId('username');
    var r = byId('role');
    var username = u ? String(u.value || '').trim() : '';
    if (!username) { return; }
    req('POST', '/users', {username: username, role: r ? (r.value || 'user') : 'user', enabled: true}, function () {
      if (u) { u.value = ''; }
      reloadAll();
    });
  }
  function updateUser(username) {
    var roleEl = byId('role-' + username);
    var onEl = byId('on-' + username);
    req('PUT', '/users/' + encodeURIComponent(username), {
      role: roleEl ? roleEl.value : null,
      enabled: onEl ? !!onEl.checked : null,
    }, function () { reloadAll(); });
  }
  function delUser(username) {
    req('DELETE', '/users/' + encodeURIComponent(username), null, function () { reloadAll(); });
  }
  function runSelfCheck() {
    var report = {
      ts: Math.floor(Date.now() / 1000),
      mode: 'external-runtime',
      location: window.location.href,
      runtime_loaded: !!window.__OS_WEB_RUNTIME_LOADED,
      checks: {},
    };
    function put(name, ok, status, sample) {
      report.checks[name] = {ok: !!ok, status: status, sample: String(sample || '')};
      setText('selfCheckView', JSON.stringify(report, null, 2));
    }
    req('GET', '/api/health', null, function (e1, d1) {
      put('health', !e1, e1 ? 'error' : 200, e1 ? String(e1) : JSON.stringify(d1 || {}).slice(0, 120));
    });
    req('GET', '/api/overview', null, function (e2, d2) {
      put('overview', !e2, e2 ? 'error' : 200, e2 ? String(e2) : JSON.stringify(d2 || {}).slice(0, 120));
    });
    req('GET', '/api/web_runtime.js', null, function (e3, _d3) {
      put('runtime_js', !e3, e3 ? 'error' : 200, e3 ? String(e3) : 'runtime script reachable');
    });
  }
  function bindUiHandlers() {
    var nav = document.querySelectorAll('.nav-btn[data-target]');
    for (var i = 0; i < nav.length; i++) {
      nav[i].addEventListener('click', function (evt) {
        var target = evt.currentTarget ? evt.currentTarget.getAttribute('data-target') : null;
        if (!target) { return; }
        var sections = document.querySelectorAll('.section');
        for (var s = 0; s < sections.length; s++) { sections[s].classList.remove('show'); }
        var sec = byId('sec-' + target);
        if (sec) { sec.classList.add('show'); }
      });
    }
    var examples = document.querySelectorAll('.cmd-example[data-cmd]');
    for (var j = 0; j < examples.length; j++) {
      examples[j].addEventListener('click', function (evt) {
        var cmd = evt.currentTarget ? evt.currentTarget.getAttribute('data-cmd') : '';
        var line = byId('cmdLine');
        if (line && cmd) { line.value = cmd; }
      });
    }
    function wire(id, fn) {
      var el = byId(id);
      if (el) { el.addEventListener('click', fn); }
    }
    wire('refreshBtn', reloadAll);
    wire('selfCheckBtn', runSelfCheck);
    wire('pluginRunBtn', runPluginAction);
    wire('transportApplyBtn', toggleTransport);
    wire('transportReloadBtn', reloadTransport);
    wire('configGetBtn', getConfig);
    wire('configSetBtn', setConfig);
    wire('userAddBtn', addUser);
    wire('userReloadBtn', reloadAll);
    wire('consoleRunBtn', runCommandLine);
    wire('consoleHelpBtn', loadCommandHelp);
    var usersTable = byId('users');
    if (usersTable) {
      usersTable.addEventListener('click', function (evt) {
        var t = evt.target || evt.srcElement;
        if (!t || !t.getAttribute) { return; }
        var action = t.getAttribute('data-user-action');
        var username = t.getAttribute('data-username');
        if (!action || !username) { return; }
        if (action === 'update') { updateUser(username); }
        if (action === 'delete') { delUser(username); }
      });
    }
  }
  window.reloadAll = window.reloadAll || reloadAll;
  window.setCmd = window.setCmd || setCmd;
  window.runCommandLine = window.runCommandLine || runCommandLine;
  window.loadCommandHelp = window.loadCommandHelp || loadCommandHelp;
  window.runPluginAction = window.runPluginAction || runPluginAction;
  window.toggleTransport = window.toggleTransport || toggleTransport;
  window.reloadTransport = window.reloadTransport || reloadTransport;
  window.getConfig = window.getConfig || getConfig;
  window.setConfig = window.setConfig || setConfig;
  window.addUser = window.addUser || addUser;
  window.updateUser = window.updateUser || updateUser;
  window.delUser = window.delUser || delUser;
  window.runSelfCheck = window.runSelfCheck || runSelfCheck;
  window.__OS_WEB_RUNTIME_LOADED = true;
  setBanner('warn', 'Connecting to web service...');
  setTimeout(bindUiHandlers, 100);
  setTimeout(reloadAll, 50);
  setInterval(reloadAll, 3000);
  setTimeout(runSelfCheck, 350);
})();
"""

    @staticmethod
    def _frontend_html():
        return """<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <title>OpenSynaptic Router Admin</title>
  <style>
    :root {
      --bg: #0e1422;
      --panel: #141d2f;
      --panel-2: #1a263d;
      --text: #e7edf8;
      --muted: #93a2bf;
      --line: #2c3b58;
      --accent: #38bdf8;
      --accent-2: #22d3ee;
      --ok: #34d399;
      --warn: #f59e0b;
      --bad: #ef4444;
      --radius: 12px;
      --row-h: 42px;
    }
    body.light {
      --bg: #f3f6fb;
      --panel: #ffffff;
      --panel-2: #f8fbff;
      --text: #0f172a;
      --muted: #475569;
      --line: #d6e0ee;
      --accent: #0284c7;
      --accent-2: #0891b2;
    }
    body.compact { --row-h: 34px; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background: radial-gradient(circle at top right, #192742, var(--bg));
      min-height: 100vh;
    }
    .topbar {
      height: 56px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 16px;
      border-bottom: 1px solid var(--line);
      background: rgba(20, 29, 47, 0.9);
      backdrop-filter: blur(6px);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .brand { font-weight: 700; letter-spacing: .4px; }
    .status-dot { width: 10px; height: 10px; border-radius: 99px; display: inline-block; margin-right: 8px; background: var(--warn); }
    .ok { background: var(--ok); }
    .wrap { display: grid; grid-template-columns: 220px 1fr; min-height: calc(100vh - 56px); }
    .sidebar {
      border-right: 1px solid var(--line);
      background: rgba(20, 29, 47, 0.7);
      padding: 10px;
    }
    .nav-btn {
      width: 100%;
      text-align: left;
      border: 1px solid transparent;
      color: var(--text);
      background: transparent;
      height: var(--row-h);
      border-radius: 10px;
      padding: 0 12px;
      margin-bottom: 6px;
      cursor: pointer;
    }
    .nav-btn:hover { background: var(--panel-2); }
    .nav-btn.active { border-color: var(--accent); background: rgba(56, 189, 248, .12); }
    .main { padding: 14px; }
    .grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px; }
    .card {
      grid-column: span 12;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--panel);
      padding: 14px;
    }
    .kpi { grid-column: span 3; min-width: 180px; }
    .title { font-weight: 700; margin-bottom: 10px; }
    .muted { color: var(--muted); }
    .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    input, select, textarea, button {
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--panel-2);
      color: var(--text);
      height: var(--row-h);
      padding: 0 10px;
    }
    textarea { height: 100px; padding-top: 8px; }
    button.primary { background: linear-gradient(90deg, var(--accent), var(--accent-2)); color: #fff; border: none; }
    table { width: 100%; border-collapse: collapse; }
    th, td { border-bottom: 1px solid var(--line); padding: 8px; text-align: left; }
    .section { display: none; }
    .section.show { display: block; }
    .opt-cat { border: 1px solid var(--line); border-radius: 10px; margin-top: 10px; overflow: hidden; }
    .opt-head { background: rgba(56, 189, 248, .08); padding: 8px 10px; border-bottom: 1px solid var(--line); font-weight: 600; }
    .opt-row { display: grid; grid-template-columns: 1fr 260px 96px; gap: 8px; padding: 8px 10px; border-bottom: 1px solid var(--line); align-items: center; }
    .opt-row:last-child { border-bottom: none; }
    .opt-meta { font-size: 12px; color: var(--muted); }
    .opt-key { font-family: Consolas, monospace; font-size: 12px; color: var(--muted); }
    .opt-input { width: 100%; }
    .conn-banner {
      display: block;
      padding: 8px 14px;
      border-bottom: 1px solid var(--line);
      font-size: 13px;
      background: rgba(245, 158, 11, 0.15);
      color: #fcd34d;
    }
    .conn-banner.ok {
      background: rgba(52, 211, 153, 0.12);
      color: #86efac;
    }
    .conn-banner.bad {
      background: rgba(239, 68, 68, 0.16);
      color: #fca5a5;
    }
    pre {
      margin: 0;
      border: 1px solid var(--line);
      background: rgba(0, 0, 0, .15);
      border-radius: 10px;
      padding: 10px;
      overflow: auto;
    }
  </style>
</head>
<body class='dark'>
  <div class='topbar'>
    <div class='brand'>OpenSynaptic Router Admin</div>
    <div class='row'>
      <span><span id='runningDot' class='status-dot'></span><span id='runningLabel'>service</span></span>
      <input id='token' placeholder='X-Admin-Token'>
      <button id='refreshBtn' class='primary' onclick='reloadAll()'>Refresh</button>
    </div>
  </div>
  <div id='connectionBanner' class='conn-banner'>Connecting to web service...</div>

  <div class='wrap'>
    <aside class='sidebar'>
      <button class='nav-btn active' data-target='overview' onclick='switchSection("overview")'>Overview</button>
      <button class='nav-btn' data-target='plugins' onclick='switchSection("plugins")'>Plugins</button>
      <button class='nav-btn' data-target='transport' onclick='switchSection("transport")'>Transport</button>
      <button class='nav-btn' data-target='config' onclick='switchSection("config")'>Config</button>
      <button class='nav-btn' data-target='users' onclick='switchSection("users")'>Users</button>
      <button class='nav-btn' data-target='console' onclick='switchSection("console")'>Command Console</button>
      <button class='nav-btn' data-target='options' onclick='switchSection("options")'>UI Options</button>
    </aside>

    <main class='main'>
      <section id='sec-overview' class='section show'>
        <div class='grid'>
          <div class='card kpi'><div class='muted'>Device</div><div id='kpiDevice'>-</div></div>
          <div class='card kpi'><div class='muted'>Assigned ID</div><div id='kpiAid'>-</div></div>
          <div class='card kpi'><div class='muted'>Core</div><div id='kpiCore'>-</div></div>
          <div class='card kpi'><div class='muted'>Uptime</div><div id='kpiUp'>-</div></div>
          <div class='card kpi'><div class='muted'>Run Status</div><div id='runStatus'>idle</div></div>
          <div class='card kpi'><div class='muted'>Packets</div><div id='runPackets'>0</div></div>
          <div class='card kpi'><div class='muted'>Avg Latency (ms)</div><div id='runLatency'>0.0</div></div>
          <div class='card kpi'><div class='muted'>Tick Errors</div><div id='runErrors'>0</div></div>
          <div class='card'><div class='title'>Performance Stats</div><pre id='perfStatsView'>loading...</pre></div>
          <div class='card'><div class='title'>Recent CLI Jobs</div><pre id='jobStatsView'>loading...</pre></div>
          <div class='card'>
            <div class='title'>Frontend Self-check</div>
            <div class='row'>
              <button id='selfCheckBtn' onclick='runSelfCheck()'>Run Self-check</button>
              <span class='muted' id='selfCheckHint'>Checks api health, overview, runtime script, and browser features.</span>
            </div>
            <pre id='selfCheckView'>not started</pre>
          </div>
        </div>
      </section>

      <section id='sec-plugins' class='section'>
        <div class='card'>
          <div class='title'>Plugin Control</div>
          <div class='row'>
            <input id='pluginName' value='web_user' placeholder='plugin name'>
            <select id='pluginAction'>
              <option value='load'>load</option>
              <option value='start'>start</option>
              <option value='stop'>stop</option>
              <option value='cmd'>cmd</option>
            </select>
            <input id='pluginSubCmd' placeholder='sub command'>
            <input id='pluginArgs' placeholder='args JSON array'>
            <button id='pluginRunBtn' class='primary' onclick='runPluginAction()'>Run</button>
          </div>
          <pre id='pluginResult' class='muted'></pre>
        </div>
      </section>

      <section id='sec-transport' class='section'>
        <div class='card'>
          <div class='title'>Transport Control</div>
          <div class='row'>
            <input id='medium' placeholder='udp/tcp/uart/...'>
            <select id='mediumState'><option value='true'>enable</option><option value='false'>disable</option></select>
            <button id='transportApplyBtn' class='primary' onclick='toggleTransport()'>Apply</button>
            <button id='transportReloadBtn' onclick='reloadTransport()'>Reload Driver</button>
          </div>
          <pre id='transportResult' class='muted'></pre>
        </div>
      </section>

      <section id='sec-config' class='section'>
        <div class='card'>
          <div class='title'>Config Editor</div>
          <div class='row'>
            <input id='cfgKey' placeholder='dotted key path'>
            <select id='cfgType'>
              <option value='json'>json</option>
              <option value='str'>str</option>
              <option value='int'>int</option>
              <option value='float'>float</option>
              <option value='bool'>bool</option>
            </select>
            <button id='configGetBtn' onclick='getConfig()'>Get</button>
            <button id='configSetBtn' class='primary' onclick='setConfig()'>Set</button>
          </div>
          <textarea id='cfgValue' placeholder='value'></textarea>
          <pre id='configResult' class='muted'></pre>
        </div>
      </section>

      <section id='sec-users' class='section'>
        <div class='card'>
          <div class='title'>User Manager</div>
          <div class='row'>
            <input id='username' placeholder='username'>
            <input id='role' placeholder='role (user/admin)' value='user'>
            <button id='userAddBtn' class='primary' onclick='addUser()'>Add User</button>
            <button id='userReloadBtn' onclick='reloadUsers()'>Reload</button>
          </div>
          <table>
            <thead><tr><th>User</th><th>Role</th><th>Enabled</th><th>Actions</th></tr></thead>
            <tbody id='users'></tbody>
          </table>
        </div>
      </section>

      <section id='sec-console' class='section'>
        <div class='card'>
          <div class='title'>Command Console</div>
          <div class='row'>
            <input id='cmdLine' placeholder='e.g. plugin-test --suite component' style='min-width:420px;'>
            <button id='consoleRunBtn' class='primary' onclick='runCommandLine()'>Run</button>
            <button id='consoleHelpBtn' onclick='loadCommandHelp()'>Help</button>
            <button id='consoleToggleOutputBtn' onclick='toggleFullCmdOutput()'>Toggle Full Output</button>
          </div>
          <div class='row'>
            <span class='muted'>Quick examples:</span>
            <button class='cmd-example' data-cmd='status' onclick='setCmd("status")'>status</button>
            <button class='cmd-example' data-cmd='plugin-test --suite component' onclick='setCmd("plugin-test --suite component")'>plugin-test component</button>
            <button class='cmd-example' data-cmd='plugin-test --suite stress --workers 2 --total 20' onclick='setCmd("plugin-test --suite stress --workers 2 --total 20")'>plugin-test stress</button>
            <button class='cmd-example' data-cmd='pipeline-info' onclick='setCmd("pipeline-info")'>pipeline-info</button>
          </div>
          <pre id='cmdResult' class='muted'></pre>
          <pre id='cmdOutputPreview' class='muted'></pre>
          <pre id='cmdOutputFull' class='muted' style='display:none; max-height:420px; overflow:auto;'></pre>
        </div>
      </section>

      <section id='sec-options' class='section'>
        <div class='card'>
          <div class='title'>UI Options</div>
          <div class='row'>
            <select id='uiTheme'>
              <option value='router-dark'>router-dark</option>
              <option value='router-light'>router-light</option>
            </select>
            <select id='uiLayout'>
              <option value='sidebar'>sidebar</option>
            </select>
            <input id='uiRefresh' type='number' min='1' value='3'>
            <label><input id='uiCompact' type='checkbox' style='height:auto'> compact</label>
            <button id='uiSaveBtn' class='primary' onclick='saveUiOptions()'>Save UI</button>
          </div>
          <pre id='uiResult' class='muted'></pre>
        </div>
        <div class='card'>
          <div class='title'>Auto Option Studio</div>
          <div class='row'>
            <label><input id='onlyWritable' type='checkbox' checked style='height:auto'> writable only</label>
            <button id='optionsReloadBtn' onclick='loadOptionSchema()'>Reload Options</button>
            <button id='optionsApplyBtn' class='primary' onclick='applyDirtyOptions()'>Apply Changed</button>
          </div>
          <div id='optionSchemaView' class='muted'>loading option schema...</div>
          <pre id='optionApplyResult' class='muted'></pre>
        </div>
      </section>
    </main>
  </div>

  <script src='/api/web_runtime.js'></script>

  <script>
    (function () {
      // If external runtime is blocked too, keep a visible hint for diagnosis.
      setTimeout(function () {
        if (!window.__OS_WEB_RUNTIME_LOADED) {
          var el = document.getElementById('connectionBanner');
          if (el) {
            el.className = 'conn-banner bad';
            el.textContent = 'Runtime script failed to load. Try Ctrl+F5, disable cache, or check browser script policy.';
          }
        }
      }, 1500);
    })();
  </script>

  <script>
    // ES5 fallback runtime: keeps dashboard and command console alive even when modern JS parsing fails.
    (function () {
      function byId(id) { return document.getElementById(id); }
      function safeText(id, v) { var el = byId(id); if (el) { el.textContent = String(v); } }
      function tokenHeader() {
        var el = byId('token');
        var token = el ? String(el.value || '').trim() : '';
        return token ? {'X-Admin-Token': token} : {};
      }
      function setBanner(state, msg) {
        var el = byId('connectionBanner');
        if (!el) { return; }
        el.className = 'conn-banner' + (state === 'ok' ? ' ok' : (state === 'bad' ? ' bad' : ''));
        el.textContent = msg;
      }
      function requestJson(method, path, body, cb) {
        var xhr = new XMLHttpRequest();
        xhr.open(method, path, true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        var hdr = tokenHeader();
        if (hdr['X-Admin-Token']) { xhr.setRequestHeader('X-Admin-Token', hdr['X-Admin-Token']); }
        xhr.onreadystatechange = function () {
          if (xhr.readyState !== 4) { return; }
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              var data = JSON.parse(xhr.responseText || '{}');
              setBanner('ok', 'Connected to web service.');
              cb(null, data);
            } catch (e) {
              setBanner('bad', 'Disconnected: invalid JSON response');
              cb(e || new Error('invalid json'));
            }
            return;
          }
          setBanner('bad', 'Disconnected from web service: HTTP ' + String(xhr.status));
          cb(new Error('http ' + String(xhr.status)));
        };
        try {
          xhr.send(body ? JSON.stringify(body) : null);
        } catch (e) {
          setBanner('bad', 'Disconnected from web service: network error');
          cb(e || new Error('network error'));
        }
      }
      window.switchSection = window.switchSection || function (name) {
        var sections = document.querySelectorAll('.section');
        for (var i = 0; i < sections.length; i++) { sections[i].classList.remove('show'); }
        var target = byId('sec-' + name);
        if (target) { target.classList.add('show'); }
      };
      window.setCmd = window.setCmd || function (text) {
        var el = byId('cmdLine');
        if (el) { el.value = text; }
      };
      window.reloadUsers = window.reloadUsers || function () {
        requestJson('GET', '/users', null, function (_err, data) {
          if (_err || !data) { return; }
          var rows = data.users || [];
          var html = '';
          for (var i = 0; i < rows.length; i++) {
            var u = rows[i] || {};
            var uname = String(u.username || '');
            var role = String(u.role || 'user');
            var checked = u.enabled ? 'checked' : '';
            html += '<tr>' +
              '<td>' + uname + '</td>' +
              '<td><input id="role-' + uname + '" value="' + role + '"></td>' +
              '<td><input id="on-' + uname + '" type="checkbox" ' + checked + '></td>' +
              '<td><button data-user-action="update" data-username="' + uname + '">Update</button> <button data-user-action="delete" data-username="' + uname + '">Delete</button></td>' +
              '</tr>';
          }
          var tb = byId('users');
          if (tb) { tb.innerHTML = html; }
        });
      };
      window.reloadAll = window.reloadAll || function () {
        requestJson('GET', '/api/overview', null, function (err, payload) {
          if (err || !payload) {
            safeText('perfStatsView', 'Failed to load overview.');
            return;
          }
          var d = payload.overview || {};
          var idn = d.identity || {};
          var svc = d.service || {};
          var m = d.overview_metrics || {};
          var run = m.run_stats || {};
          var perf = m.performance_stats || {};
          var jobs = m.jobs || {};
          safeText('runningLabel', svc.running ? 'service running' : 'service stopped');
          safeText('kpiDevice', idn.device_id || '-');
          safeText('kpiAid', idn.assigned_id == null ? '-' : idn.assigned_id);
          safeText('kpiCore', idn.core_backend || '-');
          safeText('kpiUp', String(svc.uptime_s || 0) + ' s');
          safeText('runStatus', run.status || 'idle');
          safeText('runPackets', run.packets_processed || 0);
          safeText('runLatency', run.avg_packet_latency_ms || 0.0);
          safeText('runErrors', run.tick_errors || 0);
          safeText('perfStatsView', JSON.stringify(perf, null, 2));
          safeText('jobStatsView', JSON.stringify({total: jobs.total || 0, recent: jobs.recent || []}, null, 2));
          window.reloadUsers();
        });
      };
      window.runCommandLine = window.runCommandLine || function () {
        var el = byId('cmdLine');
        var line = el ? String(el.value || '').trim() : '';
        if (!line) { return; }
        requestJson('POST', '/api/oscli/execute', {command: line, background: true}, function (err, data) {
          safeText('cmdResult', JSON.stringify(data || {ok: false, error: String(err || 'request failed')}, null, 2));
        });
      };
      window.addUser = window.addUser || function () {
        var u = byId('username');
        var r = byId('role');
        var username = u ? String(u.value || '').trim() : '';
        var role = r ? String(r.value || '').trim() : 'user';
        if (!username) { return; }
        requestJson('POST', '/users', {username: username, role: role || 'user', enabled: true}, function () {
          if (u) { u.value = ''; }
          if (window.reloadUsers) { window.reloadUsers(); }
        });
      };
      window.updateUser = window.updateUser || function (username) {
        var roleEl = byId('role-' + username);
        var onEl = byId('on-' + username);
        requestJson('PUT', '/users/' + encodeURIComponent(username), {
          role: roleEl ? roleEl.value : null,
          enabled: onEl ? !!onEl.checked : null,
        }, function () {
          if (window.reloadUsers) { window.reloadUsers(); }
        });
      };
      window.delUser = window.delUser || function (username) {
        requestJson('DELETE', '/users/' + encodeURIComponent(username), null, function () {
          if (window.reloadUsers) { window.reloadUsers(); }
        });
      };
      window.loadCommandHelp = window.loadCommandHelp || function () {
        requestJson('POST', '/api/oscli/execute', {command: 'help --full', background: false}, function (err, data) {
          safeText('cmdResult', JSON.stringify(data || {ok: false, error: String(err || 'request failed')}, null, 2));
        });
      };
      function bindUiHandlers() {
        var nav = document.querySelectorAll('.nav-btn[data-target]');
        for (var i = 0; i < nav.length; i++) {
          nav[i].addEventListener('click', function (evt) {
            var target = evt.currentTarget ? evt.currentTarget.getAttribute('data-target') : null;
            if (target && window.switchSection) { window.switchSection(target); }
          });
        }
        var examples = document.querySelectorAll('.cmd-example[data-cmd]');
        for (var j = 0; j < examples.length; j++) {
          examples[j].addEventListener('click', function (evt) {
            var cmd = evt.currentTarget ? evt.currentTarget.getAttribute('data-cmd') : '';
            if (cmd && window.setCmd) { window.setCmd(cmd); }
          });
        }
        function wire(id, fn) {
          var el = byId(id);
          if (el) { el.addEventListener('click', fn); }
        }
        wire('refreshBtn', function () { if (window.reloadAll) { window.reloadAll(); } });
        wire('selfCheckBtn', function () { if (window.runSelfCheck) { window.runSelfCheck(); } });
        wire('pluginRunBtn', function () { if (window.runPluginAction) { window.runPluginAction(); } });
        wire('transportApplyBtn', function () { if (window.toggleTransport) { window.toggleTransport(); } });
        wire('transportReloadBtn', function () { if (window.reloadTransport) { window.reloadTransport(); } });
        wire('configGetBtn', function () { if (window.getConfig) { window.getConfig(); } });
        wire('configSetBtn', function () { if (window.setConfig) { window.setConfig(); } });
        wire('userAddBtn', function () { if (window.addUser) { window.addUser(); } });
        wire('userReloadBtn', function () { if (window.reloadUsers) { window.reloadUsers(); } });
        wire('consoleRunBtn', function () { if (window.runCommandLine) { window.runCommandLine(); } });
        wire('consoleHelpBtn', function () { if (window.loadCommandHelp) { window.loadCommandHelp(); } });
        wire('consoleToggleOutputBtn', function () { if (window.toggleFullCmdOutput) { window.toggleFullCmdOutput(); } });
        wire('uiSaveBtn', function () { if (window.saveUiOptions) { window.saveUiOptions(); } });
        wire('optionsReloadBtn', function () { if (window.loadOptionSchema) { window.loadOptionSchema(); } });
        wire('optionsApplyBtn', function () { if (window.applyDirtyOptions) { window.applyDirtyOptions(); } });
        var usersTable = byId('users');
        if (usersTable) {
          usersTable.addEventListener('click', function (evt) {
            var t = evt.target || evt.srcElement;
            if (!t || !t.getAttribute) { return; }
            var action = t.getAttribute('data-user-action');
            var username = t.getAttribute('data-username');
            if (!action || !username) { return; }
            if (action === 'update' && window.updateUser) { window.updateUser(username); }
            if (action === 'delete' && window.delUser) { window.delUser(username); }
          });
        }
      }
      window.runSelfCheck = window.runSelfCheck || function () {
        var report = {
          ts: Math.floor(Date.now() / 1000),
          mode: 'fallback',
          location: window.location.href,
          runtime_loaded: !!window.__OS_WEB_RUNTIME_LOADED,
          checks: {},
        };
        function put(name, ok, status, sample) {
          report.checks[name] = {ok: !!ok, status: status, sample: String(sample || '')};
          safeText('selfCheckView', JSON.stringify(report, null, 2));
        }
        requestJson('GET', '/api/health', null, function (e1, d1) {
          put('health', !e1, e1 ? 'error' : 200, e1 ? String(e1) : JSON.stringify(d1 || {}).slice(0, 120));
        });
        requestJson('GET', '/api/overview', null, function (e2, d2) {
          put('overview', !e2, e2 ? 'error' : 200, e2 ? String(e2) : JSON.stringify(d2 || {}).slice(0, 120));
        });
        requestJson('GET', '/api/web_runtime.js', null, function (e3, d3) {
          put('runtime_js', !e3, e3 ? 'error' : 200, e3 ? String(e3) : JSON.stringify(d3 || {}).slice(0, 120));
        });
      };
      setBanner('warn', 'Connecting to web service...');
      setTimeout(bindUiHandlers, 120);
      setTimeout(window.reloadAll, 80);
      setInterval(window.reloadAll, 3000);
      setTimeout(function () { if (window.runSelfCheck) { window.runSelfCheck(); } }, 350);
    })();
  </script>

  <script>
    let dashboardCache = null;
    let uiConfig = null;
    let refreshTimer = null;
    let optionSchema = null;
    const dirtyOptions = {};
    let cmdShowFullOutput = false;
    let currentJobId = null;
    let connectionFailures = 0;
    let connectionRetryAtMs = 0;

    function setConnectionBanner(state, message) {
      const el = document.getElementById('connectionBanner');
      if (!el) return;
      el.classList.remove('ok', 'bad');
      if (state === 'ok') {
        el.classList.add('ok');
      } else if (state === 'bad') {
        el.classList.add('bad');
      }
      el.textContent = message;
    }

    function noteConnectionSuccess() {
      connectionFailures = 0;
      connectionRetryAtMs = 0;
      setConnectionBanner('ok', 'Connected to web service.');
    }

    function noteConnectionFailure(message) {
      connectionFailures += 1;
      connectionRetryAtMs = Date.now() + 3000;
      setConnectionBanner('bad', 'Disconnected from web service: ' + String(message || 'request failed') + ' (auto retrying...)');
    }

    function tokenHeader() {
      const token = document.getElementById('token').value.trim();
      return token ? {'X-Admin-Token': token} : {};
    }

    async function api(path, method='GET', body=null) {
      const headers = Object.assign({'Content-Type': 'application/json'}, tokenHeader());
      try {
        const r = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : null });
        if (!r.ok) {
          const txt = await r.text();
          throw new Error('HTTP ' + String(r.status) + ': ' + txt.slice(0, 180));
        }
        const data = await r.json();
        noteConnectionSuccess();
        return data;
      } catch (err) {
        noteConnectionFailure(err && err.message ? err.message : 'network error');
        throw err;
      }
    }

    function switchSection(name) {
      document.querySelectorAll('.section').forEach(s => s.classList.remove('show'));
      const target = document.getElementById('sec-' + name);
      if (target) target.classList.add('show');
      document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
      const nav = document.querySelector('.nav-btn[data-target="' + name + '"]');
      if (nav) nav.classList.add('active');
    }

    function bindUiHandlers() {
      document.querySelectorAll('.nav-btn[data-target]').forEach(btn => {
        btn.addEventListener('click', () => {
          const target = btn.getAttribute('data-target');
          if (target) switchSection(target);
        });
      });
      document.querySelectorAll('.cmd-example[data-cmd]').forEach(btn => {
        btn.addEventListener('click', () => {
          const cmd = btn.getAttribute('data-cmd') || '';
          if (cmd) setCmd(cmd);
        });
      });
      const wire = (id, fn) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('click', fn);
      };
      wire('refreshBtn', () => reloadAll());
      wire('selfCheckBtn', () => runSelfCheck());
      wire('pluginRunBtn', () => runPluginAction());
      wire('transportApplyBtn', () => toggleTransport());
      wire('transportReloadBtn', () => reloadTransport());
      wire('configGetBtn', () => getConfig());
      wire('configSetBtn', () => setConfig());
      wire('userAddBtn', () => addUser());
      wire('userReloadBtn', () => reloadUsers());
      wire('consoleRunBtn', () => runCommandLine());
      wire('consoleHelpBtn', () => loadCommandHelp());
      wire('consoleToggleOutputBtn', () => toggleFullCmdOutput());
      wire('uiSaveBtn', () => saveUiOptions());
      wire('optionsReloadBtn', () => loadOptionSchema());
      wire('optionsApplyBtn', () => applyDirtyOptions());
      const usersTable = document.getElementById('users');
      if (usersTable) {
        usersTable.addEventListener('click', (evt) => {
          const target = evt.target;
          if (!(target instanceof HTMLElement)) return;
          const action = target.getAttribute('data-user-action');
          const username = target.getAttribute('data-username');
          if (!action || !username) return;
          if (action === 'update') {
            updateUser(username);
          } else if (action === 'delete') {
            delUser(username);
          }
        });
      }
    }

    function applyTheme() {
      const body = document.body;
      const light = uiConfig && uiConfig.ui_theme === 'router-light';
      body.classList.toggle('light', light);
      body.classList.toggle('compact', !!(uiConfig && uiConfig.ui_compact));
    }

    async function loadUiOptions() {
      const payload = await api('/api/ui/config');
      uiConfig = payload.ui || {};
      document.getElementById('uiTheme').value = uiConfig.ui_theme || 'router-dark';
      document.getElementById('uiLayout').value = uiConfig.ui_layout || 'sidebar';
      document.getElementById('uiRefresh').value = uiConfig.ui_refresh_seconds || 3;
      document.getElementById('uiCompact').checked = !!uiConfig.ui_compact;
      applyTheme();
      resetRefreshTimer();
    }

    async function saveUiOptions() {
      const body = {
        ui_theme: document.getElementById('uiTheme').value,
        ui_layout: document.getElementById('uiLayout').value,
        ui_refresh_seconds: parseInt(document.getElementById('uiRefresh').value || '3', 10),
        ui_compact: document.getElementById('uiCompact').checked
      };
      const payload = await api('/api/ui/config', 'PUT', body);
      uiConfig = (payload && payload.ui) || uiConfig;
      document.getElementById('uiResult').textContent = JSON.stringify(payload, null, 2);
      applyTheme();
      resetRefreshTimer();
    }

    function valueTypeForField(field) {
      return (field && field.type) ? field.type : 'json';
    }

    function toFieldValue(raw, fieldType) {
      if (fieldType === 'bool') return String(raw) === 'true';
      if (fieldType === 'int') return parseInt(String(raw || '0'), 10);
      if (fieldType === 'float') return parseFloat(String(raw || '0'));
      if (fieldType === 'json') {
        if (typeof raw === 'string') {
          const text = raw.trim();
          if (!text) return null;
          return JSON.parse(text);
        }
        return raw;
      }
      return String(raw ?? '');
    }

    function escapeHtml(text) {
      return String(text ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
    }

    function renderFieldInput(field) {
      const key = field.key;
      const fid = 'opt-' + key.replace(/[^a-zA-Z0-9_]/g, '_');
      const writable = !!field.writable;
      if (field.type === 'bool') {
        const cur = String(!!field.value);
        return `<select class='opt-input' id='${fid}' data-opt-key='${escapeHtml(key)}' data-opt-type='bool' ${writable ? '' : 'disabled'}>
            <option value='true' ${cur === 'true' ? 'selected' : ''}>true</option>
            <option value='false' ${cur === 'false' ? 'selected' : ''}>false</option>
          </select>`;
      }
      if (field.type === 'int' || field.type === 'float') {
        return `<input class='opt-input' id='${fid}' data-opt-key='${escapeHtml(key)}' data-opt-type='${field.type}' type='number' value='${escapeHtml(field.value)}' ${writable ? '' : 'disabled'}>`;
      }
      if (field.type === 'json') {
        return `<textarea class='opt-input' id='${fid}' data-opt-key='${escapeHtml(key)}' data-opt-type='json' ${writable ? '' : 'disabled'}>${escapeHtml(JSON.stringify(field.value, null, 2))}</textarea>`;
      }
      return `<input class='opt-input' id='${fid}' data-opt-key='${escapeHtml(key)}' data-opt-type='str' type='text' value='${escapeHtml(field.value)}' ${writable ? '' : 'disabled'}>`;
    }

    function bindOptionInputs() {
      document.querySelectorAll('[data-opt-key]').forEach(el => {
        const eventName = el.tagName === 'SELECT' ? 'change' : 'input';
        el.addEventListener(eventName, () => {
          const key = el.getAttribute('data-opt-key');
          const fieldType = el.getAttribute('data-opt-type') || 'json';
          const raw = (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT' || el.tagName === 'SELECT') ? el.value : '';
          dirtyOptions[key] = { key, value_type: fieldType, raw_value: raw };
        });
      });
    }

    function renderOptionSchema(schemaPayload) {
      const target = document.getElementById('optionSchemaView');
      const schema = (schemaPayload && schemaPayload.schema) || { categories: [] };
      optionSchema = schema;
      const chunks = (schema.categories || []).map(cat => {
        const rows = (cat.fields || []).map(field => {
          const state = field.writable ? 'writable' : 'read-only';
          return `<div class='opt-row'>
            <div>
              <div><strong>${escapeHtml(field.label)}</strong></div>
              <div class='opt-meta'>${escapeHtml(field.description || '')}</div>
              <div class='opt-key'>${escapeHtml(field.key)} (${escapeHtml(field.type)} / ${state})</div>
            </div>
            <div>${renderFieldInput(field)}</div>
            <div>
              <button ${field.writable ? '' : 'disabled'} onclick='applySingleOption("${escapeHtml(field.key)}")'>Apply</button>
            </div>
          </div>`;
        }).join('');
        return `<div class='opt-cat'><div class='opt-head'>${escapeHtml(cat.title)} (${cat.count})</div>${rows}</div>`;
      }).join('');
      target.innerHTML = chunks || '<div class="muted">No option fields available.</div>';
      bindOptionInputs();
    }

    async function loadOptionSchema() {
      const onlyWritable = document.getElementById('onlyWritable').checked;
      const payload = await api('/api/options/schema?only_writable=' + (onlyWritable ? '1' : '0'));
      renderOptionSchema(payload);
    }

    function _readFieldValueByKey(key) {
      const fid = 'opt-' + key.replace(/[^a-zA-Z0-9_]/g, '_');
      const el = document.getElementById(fid);
      if (!el) return null;
      return {
        raw: el.value,
        fieldType: el.getAttribute('data-opt-type') || 'json',
      };
    }

    async function applySingleOption(key) {
      const info = _readFieldValueByKey(key);
      if (!info) return;
      let parsed;
      try {
        parsed = toFieldValue(info.raw, info.fieldType);
      } catch (err) {
        document.getElementById('optionApplyResult').textContent = JSON.stringify({ok: false, key, error: String(err)}, null, 2);
        return;
      }
      const payload = await api('/api/config', 'PUT', { key, value: parsed, value_type: info.fieldType });
      document.getElementById('optionApplyResult').textContent = JSON.stringify(payload, null, 2);
      await reloadAll();
      await loadOptionSchema();
    }

    async function applyDirtyOptions() {
      const updates = [];
      for (const key of Object.keys(dirtyOptions)) {
        const item = dirtyOptions[key];
        try {
          updates.push({ key: item.key, value_type: item.value_type, value: toFieldValue(item.raw_value, item.value_type) });
        } catch (err) {
          document.getElementById('optionApplyResult').textContent = JSON.stringify({ok: false, key: item.key, error: String(err)}, null, 2);
          return;
        }
      }
      if (!updates.length) {
        document.getElementById('optionApplyResult').textContent = JSON.stringify({ok: true, changed: [], info: 'no dirty fields'}, null, 2);
        return;
      }
      const payload = await api('/api/options', 'PUT', { updates });
      document.getElementById('optionApplyResult').textContent = JSON.stringify(payload, null, 2);
      Object.keys(dirtyOptions).forEach(k => delete dirtyOptions[k]);
      await reloadAll();
      await loadOptionSchema();
    }

    function resetRefreshTimer() {
      if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
      }
      const sec = Math.max(1, parseInt((uiConfig && uiConfig.ui_refresh_seconds) || 3, 10));
      refreshTimer = setInterval(() => {
        if (document.hidden) return;
        if (connectionRetryAtMs && Date.now() < connectionRetryAtMs) return;
        reloadAll();
      }, sec * 1000);
    }

    function renderOverview(payload) {
      const d = (payload && payload.overview) ? payload.overview : ((payload && payload.dashboard) || {});
      const idn = d.identity || {};
      const svc = d.service || {};
      const metrics = d.overview_metrics || {};
      const run = metrics.run_stats || {};
      const perf = metrics.performance_stats || {};
      const jobs = metrics.jobs || {};
      const running = !!svc.running;
      document.getElementById('runningDot').classList.toggle('ok', running);
      document.getElementById('runningLabel').textContent = running ? 'service running' : 'service stopped';
      document.getElementById('kpiDevice').textContent = idn.device_id || '-';
      document.getElementById('kpiAid').textContent = String(idn.assigned_id ?? '-');
      document.getElementById('kpiCore').textContent = idn.core_backend || '-';
      document.getElementById('kpiUp').textContent = String(svc.uptime_s || 0) + ' s';
      document.getElementById('runStatus').textContent = String(run.status || 'idle');
      document.getElementById('runPackets').textContent = String(run.packets_processed || 0);
      document.getElementById('runLatency').textContent = String(run.avg_packet_latency_ms || 0.0);
      document.getElementById('runErrors').textContent = String(run.tick_errors || 0);
      document.getElementById('perfStatsView').textContent = JSON.stringify(perf, null, 2);
      document.getElementById('jobStatsView').textContent = JSON.stringify({total: jobs.total || 0, recent: jobs.recent || []}, null, 2);
    }

    async function reloadAll() {
      const overviewPayload = await api('/api/overview');
      dashboardCache = overviewPayload;
      renderOverview(overviewPayload);
      try {
        await reloadUsers();
      } catch (_e) {
        // Keep dashboard alive even if users API is temporarily unavailable.
      }
    }

    async function reloadUsers() {
      const payload = await api('/users');
      const rows = (payload.users || []).map(u => {
        const checked = u.enabled ? 'checked' : '';
        return `<tr>
          <td>${u.username}</td>
          <td><input id='role-${u.username}' value='${u.role || 'user'}'></td>
          <td><input id='on-${u.username}' type='checkbox' ${checked}></td>
          <td>
            <button data-user-action='update' data-username='${u.username}'>Update</button>
            <button data-user-action='delete' data-username='${u.username}'>Delete</button>
          </td>
        </tr>`;
      }).join('');
      document.getElementById('users').innerHTML = rows;
    }

    async function addUser() {
      const username = document.getElementById('username').value.trim();
      const role = document.getElementById('role').value.trim() || 'user';
      if (!username) return;
      await api('/users', 'POST', {username, role, enabled: true});
      document.getElementById('username').value = '';
      await reloadUsers();
    }

    async function updateUser(username) {
      const role = document.getElementById('role-' + username).value;
      const enabled = document.getElementById('on-' + username).checked;
      await api('/users/' + encodeURIComponent(username), 'PUT', {role, enabled});
      await reloadUsers();
    }

    async function delUser(username) {
      await api('/users/' + encodeURIComponent(username), 'DELETE');
      await reloadUsers();
    }

    async function runPluginAction() {
      const plugin = document.getElementById('pluginName').value.trim();
      const action = document.getElementById('pluginAction').value;
      const sub_cmd = document.getElementById('pluginSubCmd').value.trim();
      let args = [];
      const rawArgs = document.getElementById('pluginArgs').value.trim();
      if (rawArgs) {
        try { args = JSON.parse(rawArgs); } catch (_e) { args = [rawArgs]; }
      }
      const payload = await api('/api/plugins', 'POST', {plugin, action, sub_cmd, args});
      document.getElementById('pluginResult').textContent = JSON.stringify(payload, null, 2);
      await reloadAll();
    }

    async function toggleTransport() {
      const medium = document.getElementById('medium').value.trim();
      const enabled = document.getElementById('mediumState').value === 'true';
      const payload = await api('/api/transport', 'POST', {medium, enabled});
      document.getElementById('transportResult').textContent = JSON.stringify(payload, null, 2);
      await reloadAll();
    }

    async function reloadTransport() {
      const medium = document.getElementById('medium').value.trim();
      const payload = await api('/api/transport', 'POST', {medium, reload: true});
      document.getElementById('transportResult').textContent = JSON.stringify(payload, null, 2);
      await reloadAll();
    }

    async function getConfig() {
      const key = document.getElementById('cfgKey').value.trim();
      const path = key ? '/api/config?key=' + encodeURIComponent(key) : '/api/config';
      const payload = await api(path, 'GET');
      document.getElementById('configResult').textContent = JSON.stringify(payload, null, 2);
    }

    async function setConfig() {
      const key = document.getElementById('cfgKey').value.trim();
      const valueType = document.getElementById('cfgType').value;
      const value = document.getElementById('cfgValue').value;
      const payload = await api('/api/config', 'PUT', {key, value, value_type: valueType});
      document.getElementById('configResult').textContent = JSON.stringify(payload, null, 2);
      await reloadAll();
    }

    function setCmd(text) {
      document.getElementById('cmdLine').value = text;
    }

    function clipText(text, limit) {
      const raw = String(text || '');
      const cap = Math.max(1, parseInt(String(limit || '1'), 10));
      if (raw.length <= cap) return {text: raw, truncated: false};
      return {text: raw.slice(0, cap), truncated: true};
    }

    function renderJobPayload(payload) {
      const job = ((payload || {}).job || {});
      currentJobId = job.id || currentJobId;
      const summary = {
        ok: !!(payload && payload.ok),
        id: job.id,
        command: job.command,
        status: job.status,
        exit_code: job.exit_code,
        created_at: job.created_at,
        started_at: job.started_at,
        finished_at: job.finished_at,
        stdout_len: job.stdout_len,
        stderr_len: job.stderr_len,
        error: job.error || null,
      };
      document.getElementById('cmdResult').textContent = JSON.stringify(summary, null, 2);

      const stdoutText = ('stdout' in job) ? String(job.stdout || '') : String(job.stdout_preview || '');
      const stderrText = ('stderr' in job) ? String(job.stderr || '') : String(job.stderr_preview || '');
      const merged = [stdoutText, stderrText].filter(Boolean).join('\n');
      const preview = clipText(merged, 12000);
      document.getElementById('cmdOutputPreview').textContent = preview.text + (preview.truncated ? '\n\n... [output truncated in preview]' : '');
      if (!cmdShowFullOutput) {
        document.getElementById('cmdOutputFull').textContent = '(click Toggle Full Output to load full logs)';
      } else if (!document.getElementById('cmdOutputFull').textContent || document.getElementById('cmdOutputFull').textContent === '(click Toggle Full Output to load full logs)') {
        document.getElementById('cmdOutputFull').textContent = merged || '(no output)';
      }
      document.getElementById('cmdOutputFull').style.display = cmdShowFullOutput ? 'block' : 'none';
    }

    async function toggleFullCmdOutput() {
      cmdShowFullOutput = !cmdShowFullOutput;
      document.getElementById('cmdOutputFull').style.display = cmdShowFullOutput ? 'block' : 'none';
      if (cmdShowFullOutput && currentJobId) {
        const fullPayload = await api('/api/oscli/jobs?id=' + encodeURIComponent(currentJobId) + '&include_output=1&output_limit=400000', 'GET');
        const job = (fullPayload && fullPayload.job) || {};
        const merged = [String(job.stdout || ''), String(job.stderr || '')].filter(Boolean).join('\n');
        document.getElementById('cmdOutputFull').textContent = merged || '(no output)';
      }
    }

    async function runCommandLine() {
      const line = document.getElementById('cmdLine').value.trim();
      if (!line) return;
      const payload = await api('/api/oscli/execute', 'POST', {command: line, background: true});
      renderJobPayload(payload);
      const job = (payload && payload.job) || {};
      if (job.id) {
        await pollJobUntilDone(String(job.id));
      }
      await reloadAll();
      await loadOptionSchema();
    }

    async function loadCommandHelp() {
      const payload = await api('/api/oscli/execute', 'POST', {command: 'help --full', background: false});
      renderJobPayload(payload);
    }

    async function pollJobUntilDone(jobId) {
      const startedAt = Date.now();
      const timeoutMs = 120000;
      while ((Date.now() - startedAt) < timeoutMs) {
        const payload = await api('/api/oscli/jobs?id=' + encodeURIComponent(jobId), 'GET');
        renderJobPayload(payload);
        const job = payload && payload.job;
        if (!job) return;
        const st = String(job.status || '');
        if (st === 'succeeded' || st === 'failed') {
          return;
        }
        await new Promise(resolve => setTimeout(resolve, 700));
      }
    }

    async function runSelfCheck() {
      const report = {
        ts: Math.floor(Date.now() / 1000),
        location: window.location.href,
        runtime_loaded: !!window.__OS_WEB_RUNTIME_LOADED,
        features: {
          fetch: typeof window.fetch === 'function',
          Promise: typeof window.Promise === 'function',
          classList: !!(document.body && document.body.classList),
          async_fn_available: true,
        },
        checks: {},
      };

      async function hit(name, path) {
        try {
          const r = await fetch(path, {method: 'GET', cache: 'no-store'});
          const txt = await r.text();
          report.checks[name] = {
            ok: r.ok,
            status: r.status,
            bytes: txt.length,
            sample: txt.slice(0, 120),
          };
        } catch (err) {
          report.checks[name] = {ok: false, error: String(err && err.message ? err.message : err)};
        }
      }

      await hit('health', '/api/health');
      await hit('overview', '/api/overview');
      await hit('runtime_js', '/api/web_runtime.js');
      document.getElementById('selfCheckView').textContent = JSON.stringify(report, null, 2);
      return report;
    }

    (async function init() {
      setConnectionBanner('warn', 'Connecting to web service...');
      try {
        bindUiHandlers();
      } catch (_e) {}
      try {
        await loadUiOptions();
      } catch (_e) {}
      try {
        await reloadAll();
      } catch (_e) {
        document.getElementById('perfStatsView').textContent = 'Failed to load overview. Check /api/overview.';
      }
      try {
        await loadOptionSchema();
      } catch (_e) {}
      try {
        await runSelfCheck();
      } catch (_e) {}
    })();
  </script>
</body>
</html>"""

    def _handler_cls(self):
        service = self

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                query = parse_qs(parsed.query)
                if path == '/':
                    service._refresh_settings()
                    if not bool(service._settings.get('ui_enabled', True)):
                        service._html_response(self, 403, '<h3>web_user UI is disabled by config: ui_enabled=false</h3>')
                        return
                    service._html_response(self, 200, service._frontend_html())
                    return
                if path in ('/health', '/api/health'):
                    service._json_response(self, 200, {'ok': True, 'service': 'web_user'})
                    return
                if path == '/api/web_runtime.js':
                    service._text_response(self, 200, service._runtime_js(), content_type='application/javascript; charset=utf-8')
                    return
                if path == '/users':
                    ok, code, err = service._authorize_request(self.headers, write=False, management=False)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    service._json_response(self, 200, {'users': service.list_users()})
                    return
                if path == '/api/dashboard':
                    ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    raw = str((query.get('sections', [''])[0] or '')).strip()
                    requested = [item.strip().lower() for item in raw.split(',') if item.strip()] if raw else None
                    service._json_response(self, 200, {'ok': True, 'dashboard': service.build_dashboard(sections=requested)})
                    return
                if path == '/api/ui/config':
                    ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    service._json_response(self, 200, {'ok': True, 'ui': service._ui_config_payload()})
                    return
                if path == '/api/config':
                    ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    key = str((query.get('key', [''])[0] or '')).strip()
                    try:
                        service._json_response(self, 200, service._config_get_payload(key=key or None))
                    except Exception:
                        service._json_response(self, 404, {'error': 'key not found', 'key': key})
                    return
                if path == '/api/options/schema':
                    ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    only_writable = str((query.get('only_writable', ['0'])[0] or '0')).strip().lower() in ('1', 'true', 'yes', 'on')
                    service._json_response(self, 200, {'ok': True, 'schema': service.build_option_schema(only_writable=only_writable)})
                    return
                if path == '/api/cli/help':
                    ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    service._json_response(self, 200, {'ok': True, 'commands': service.cli_help_table()})
                    return
                if path == '/api/oscli/jobs':
                    ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    include_output = str((query.get('include_output', ['0'])[0] or '0')).strip().lower() in ('1', 'true', 'yes', 'on')
                    output_limit_raw = str((query.get('output_limit', ['120000'])[0] or '120000')).strip()
                    try:
                        output_limit = max(1000, min(2000000, int(output_limit_raw or '120000')))
                    except Exception:
                        output_limit = 120000
                    job_id = str((query.get('id', [''])[0] or '')).strip()
                    if job_id:
                        job = service.get_os_cli_job(job_id, include_output=include_output, output_limit=output_limit)
                        if not job:
                            service._json_response(self, 404, {'error': 'job not found', 'id': job_id})
                            return
                        service._json_response(self, 200, {'ok': True, 'job': job})
                        return
                    limit_raw = str((query.get('limit', ['20'])[0] or '20')).strip()
                    try:
                        limit = max(1, min(200, int(limit_raw or '20')))
                    except Exception:
                        limit = 20
                    service._json_response(
                        self,
                        200,
                        {'ok': True, 'jobs': service.list_os_cli_jobs(limit=limit, include_output=include_output, output_limit=output_limit)},
                    )
                    return
                if path == '/api/oscli/metrics':
                    ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    service._json_response(self, 200, {'ok': True, 'metrics': service.get_overview_metrics()})
                    return
                if path == '/api/overview':
                    ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    service._json_response(self, 200, {'ok': True, 'overview': service.build_overview_payload()})
                    return
                if path == '/api/plugins':
                    ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    snap = service._service_snapshot()
                    service._json_response(self, 200, {'ok': True, 'plugins': snap})
                    return
                if path == '/api/transport':
                    ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    service._json_response(self, 200, {'ok': True, 'transport': service._transport_snapshot()})
                    return
                service._json_response(self, 404, {'error': 'not found'})

            def do_POST(self):
                path = urlparse(self.path).path
                if path == '/users':
                    ok, code, err = service._authorize_request(self.headers, write=True, management=False)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    payload = self._read_json()
                    username = str(payload.get('username', '')).strip()
                    if not username:
                        service._json_response(self, 400, {'error': 'username is required'})
                        return
                    ok, err = service.create_user(
                        username=username,
                        role=payload.get('role', 'user'),
                        enabled=payload.get('enabled', True),
                    )
                    if not ok:
                        service._json_response(self, 409, {'error': err})
                        return
                    service._json_response(self, 201, {'ok': True, 'username': username})
                    return
                if path == '/api/plugins':
                    ok, code, err = service._authorize_request(self.headers, write=True, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    payload = self._read_json()
                    plugin = payload.get('plugin', '')
                    action = str(payload.get('action', 'load') or 'load')
                    sub_cmd = payload.get('sub_cmd', '')
                    args = payload.get('args', []) if isinstance(payload.get('args', []), list) else []
                    ok, out = service._run_plugin_action(plugin, action, sub_cmd=sub_cmd, args=args)
                    service._json_response(self, 200 if ok else 400, out)
                    return
                if path == '/api/transport':
                    ok, code, err = service._authorize_request(self.headers, write=True, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    payload = self._read_json()
                    medium = payload.get('medium', '')
                    if bool(payload.get('reload', False)):
                        refreshed = service._reload_transport(medium)
                        service._json_response(self, 200, {'ok': bool(refreshed), 'medium': medium, 'reloaded': bool(refreshed)})
                        return
                    ok, err = service._set_transport_enabled(medium, payload.get('enabled', True))
                    if not ok:
                        service._json_response(self, 400, {'error': err, 'medium': medium})
                        return
                    service._json_response(self, 200, {'ok': True, 'medium': medium, 'enabled': bool(payload.get('enabled', True))})
                    return
                if path == '/api/cli/execute':
                    ok, code, err = service._authorize_request(self.headers, write=True, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    payload = self._read_json()
                    cmd = str(payload.get('command', '') or '').strip()
                    ok, out = service.execute_control_cli(cmd)
                    service._json_response(self, 200 if ok else 400, {'ok': ok, 'command': cmd, 'result': out})
                    return
                if path == '/api/oscli/execute':
                    ok, code, err = service._authorize_request(self.headers, write=True, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    payload = self._read_json()
                    cmd = str(payload.get('command', '') or '').strip()
                    background = bool(payload.get('background', True))
                    ok, out = service.submit_os_cli_job(command=cmd, background=background)
                    service._json_response(self, 200 if ok else 400, out)
                    return
                if path == '/api/users':
                    self.path = '/users'
                    return self.do_POST()
                if path != '/users':
                    service._json_response(self, 404, {'error': 'not found'})
                    return
                service._json_response(self, 404, {'error': 'not found'})

            def do_PUT(self):
                path = urlparse(self.path).path
                if path == '/api/ui/config':
                    ok, code, err = service._authorize_request(self.headers, write=True, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    payload = self._read_json()
                    ok, out = service._update_ui_config(payload)
                    service._json_response(self, 200 if ok else 400, out)
                    return
                if path == '/api/config':
                    ok, code, err = service._authorize_request(self.headers, write=True, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    payload = self._read_json()
                    key = str(payload.get('key', '') or '').strip()
                    if not key:
                        service._json_response(self, 400, {'error': 'key is required'})
                        return
                    ok, out = service._config_set_payload(
                        key=key,
                        value=payload.get('value', None),
                        value_type=str(payload.get('value_type', 'json') or 'json').strip().lower(),
                    )
                    service._json_response(self, 200 if ok else 403, out)
                    return
                if path == '/api/options':
                    ok, code, err = service._authorize_request(self.headers, write=True, management=True)
                    if not ok:
                        service._json_response(self, code, {'error': err})
                        return
                    payload = self._read_json()
                    ok, out = service.apply_option_updates(payload.get('updates', []))
                    service._json_response(self, 200 if ok else 400, out)
                    return
                if not path.startswith('/users/'):
                    service._json_response(self, 404, {'error': 'not found'})
                    return
                ok, code, err = service._authorize_request(self.headers, write=True, management=False)
                if not ok:
                    service._json_response(self, code, {'error': err})
                    return
                username = path.split('/users/', 1)[1].strip()
                if not username:
                    service._json_response(self, 400, {'error': 'username is required'})
                    return
                payload = self._read_json()
                ok, err = service.update_user(
                    username=username,
                    role=payload.get('role', None),
                    enabled=payload.get('enabled', None),
                )
                if not ok:
                    service._json_response(self, 404, {'error': err})
                    return
                service._json_response(self, 200, {'ok': True, 'username': username})

            def do_DELETE(self):
                path = urlparse(self.path).path
                if not path.startswith('/users/'):
                    service._json_response(self, 404, {'error': 'not found'})
                    return
                ok, code, err = service._authorize_request(self.headers, write=True, management=False)
                if not ok:
                    service._json_response(self, code, {'error': err})
                    return
                username = path.split('/users/', 1)[1].strip()
                if not username:
                    service._json_response(self, 400, {'error': 'username is required'})
                    return
                ok, err = service.delete_user(username)
                if not ok:
                    service._json_response(self, 404, {'error': err})
                    return
                service._json_response(self, 200, {'ok': True, 'username': username})

            def _read_json(self):
                try:
                    length = int(self.headers.get('Content-Length', '0') or '0')
                except Exception:
                    length = 0
                if length <= 0:
                    return {}
                raw = self.rfile.read(length)
                try:
                    return json.loads(raw.decode('utf-8'))
                except Exception:
                    return {}

            def log_message(self, fmt, *args):
                os_log.info('WEB_USER', 'HTTP', fmt % args)

        return _Handler

    def start(self, host=None, port=None):
        self._refresh_settings()
        active_host = host or self._settings.get('host', '127.0.0.1')
        active_port = int(port or self._settings.get('port', 8765))
        with self._lock:
            if self._server is not None:
                return False
            server = ThreadingHTTPServer((active_host, active_port), self._handler_cls())  # type: ignore[arg-type]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._server = server
            self._thread = thread
            self._started_at = time.time()
            os_log.info('WEB_USER', 'START', 'web user service started', {'host': active_host, 'port': active_port})
            return True

    def stop(self):
        with self._lock:
            if self._server is None:
                return False
            server = self._server
            self._server = None
            self._thread = None
            self._started_at = None
        try:
            server.shutdown()
            server.server_close()
        except Exception as exc:
            os_log.err('WEB_USER', 'STOP', exc, {})
            return False
        return True

    def close(self):
        self.stop()

    def status(self):
        with self._lock:
            return {
                'running': self._server is not None,
                'users': len(self._users.get('users', [])),
                'data_file': str(self._data_file),
                'uptime_s': round(time.time() - self._started_at, 3) if self._started_at else 0.0,
            }

    def auto_load(self):
        self._refresh_settings()
        if bool(self._settings.get('auto_start', False)):
            try:
                self.start()
            except Exception as exc:
                os_log.err('WEB_USER', 'AUTO_START', exc, {})
        return self

    def get_cli_commands(self):
        def _start(argv):
            import argparse
            p = argparse.ArgumentParser(prog='web_user start')
            p.add_argument('--host', default=self._settings.get('host', '127.0.0.1'))
            p.add_argument('--port', type=int, default=int(self._settings.get('port', 8765)))
            p.add_argument('--block', action='store_true', default=False)
            ns = p.parse_args(argv)
            ok = self.start(host=ns.host, port=ns.port)
            print(json.dumps({'started': bool(ok), 'status': self.status()}, ensure_ascii=False))
            if ok and ns.block:
                print('Web user service running in foreground. Press Ctrl+C to stop.', flush=True)
                try:
                    while self.status().get('running'):
                        time.sleep(0.5)
                except KeyboardInterrupt:
                    self.stop()
            return 0 if ok else 1

        def _stop(argv):
            _ = argv
            ok = self.stop()
            print(json.dumps({'stopped': bool(ok), 'status': self.status()}, ensure_ascii=False))
            return 0 if ok else 1

        def _status(argv):
            _ = argv
            print(json.dumps(self.status(), indent=2, ensure_ascii=False))
            return 0

        def _dashboard(argv):
            _ = argv
            print(json.dumps({'ok': True, 'dashboard': self.build_dashboard()}, indent=2, ensure_ascii=False, default=str))
            return 0

        def _cli(argv):
            import argparse
            p = argparse.ArgumentParser(prog='web_user cli')
            p.add_argument('--line', default='')
            p.add_argument('parts', nargs='*')
            ns = p.parse_args(argv)
            line = str(ns.line or '').strip()
            if not line:
                line = ' '.join([str(part) for part in ns.parts if str(part).strip()]).strip()
            ok, out = self.execute_control_cli(line)
            print(json.dumps({'ok': ok, 'command': line, 'result': out}, indent=2, ensure_ascii=False, default=str))
            return 0 if ok else 1

        def _options_schema(argv):
            import argparse
            p = argparse.ArgumentParser(prog='web_user options-schema')
            p.add_argument('--only-writable', action='store_true', default=False)
            ns = p.parse_args(argv)
            payload = {'ok': True, 'schema': self.build_option_schema(only_writable=ns.only_writable)}
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            return 0

        def _options_set(argv):
            import argparse
            p = argparse.ArgumentParser(prog='web_user options-set')
            p.add_argument('--key', required=True)
            p.add_argument('--value', required=True)
            p.add_argument('--type', dest='value_type', default='json', choices=['bool', 'int', 'float', 'str', 'json'])
            ns = p.parse_args(argv)
            ok, payload = self._config_set_payload(key=ns.key, value=ns.value, value_type=ns.value_type)
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            return 0 if ok else 1

        def _options_apply(argv):
            import argparse
            p = argparse.ArgumentParser(prog='web_user options-apply')
            p.add_argument('--updates', default='[]', help='JSON array of updates: [{"key":"a.b","value":1,"value_type":"int"}]')
            p.add_argument('--file', dest='file_path', default=None, help='Path to a JSON file that contains the updates array')
            ns = p.parse_args(argv)
            updates = []
            try:
                if ns.file_path:
                    with open(ns.file_path, 'r', encoding='utf-8') as fp:
                        updates = json.load(fp)
                else:
                    updates = json.loads(ns.updates)
            except Exception as exc:
                print(json.dumps({'ok': False, 'error': 'invalid updates payload', 'detail': str(exc)}, ensure_ascii=False))
                return 1
            ok, payload = self.apply_option_updates(updates)
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
            return 0 if bool(payload.get('ok', False)) else 1

        def _list(argv):
            _ = argv
            print(json.dumps({'users': self.list_users()}, indent=2, ensure_ascii=False))
            return 0

        def _add(argv):
            import argparse
            p = argparse.ArgumentParser(prog='web_user add')
            p.add_argument('--username', required=True)
            p.add_argument('--role', default='user')
            p.add_argument('--disabled', action='store_true', default=False)
            ns = p.parse_args(argv)
            ok, err = self.create_user(ns.username, role=ns.role, enabled=not ns.disabled)
            print(json.dumps({'ok': bool(ok), 'error': err}, ensure_ascii=False))
            return 0 if ok else 1

        def _update(argv):
            import argparse
            p = argparse.ArgumentParser(prog='web_user update')
            p.add_argument('--username', required=True)
            p.add_argument('--role', default=None)
            state = p.add_mutually_exclusive_group(required=False)
            state.add_argument('--enable', action='store_true', default=False)
            state.add_argument('--disable', action='store_true', default=False)
            ns = p.parse_args(argv)
            enabled = None
            if ns.enable:
                enabled = True
            elif ns.disable:
                enabled = False
            ok, err = self.update_user(ns.username, role=ns.role, enabled=enabled)
            print(json.dumps({'ok': bool(ok), 'error': err}, ensure_ascii=False))
            return 0 if ok else 1

        def _delete(argv):
            import argparse
            p = argparse.ArgumentParser(prog='web_user delete')
            p.add_argument('--username', required=True)
            ns = p.parse_args(argv)
            ok, err = self.delete_user(ns.username)
            print(json.dumps({'ok': bool(ok), 'error': err}, ensure_ascii=False))
            return 0 if ok else 1

        return {
            'start': _start,
            'stop': _stop,
            'status': _status,
            'dashboard': _dashboard,
            'cli': _cli,
            'options-schema': _options_schema,
            'options-set': _options_set,
            'options-apply': _options_apply,
            'list': _list,
            'add': _add,
            'update': _update,
            'delete': _delete,
        }

