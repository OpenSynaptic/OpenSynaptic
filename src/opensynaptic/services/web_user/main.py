import json
import io
import re
import shlex
import threading
import time
from contextlib import redirect_stderr, redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path

from opensynaptic.utils import os_log
from .jsonpath_utils import dotpath_get as _dotpath_get, dotpath_set as _dotpath_set, cast_value as _cast_value
from .option_schema_utils import (
    friendly_label as _friendly_label,
    infer_value_type as _infer_value_type,
    field_annotation as _field_annotation,
    flatten_option_fields as _flatten_option_fields,
    category_title as _category_title,
)


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
        self._http_stats_lock = threading.RLock()
        self._http_stats_minute_key = int(time.time() // 60)
        self._http_stats_bucket = self._new_http_stats_bucket()
        self._load_users()

    @staticmethod
    def _new_http_stats_bucket():
        return {
            'total': 0,
            'methods': {},
            'status': {},
            'status_bands': {},
            'paths': {},
        }

    @staticmethod
    def _inc_counter(counter, key):
        k = str(key or 'unknown')
        counter[k] = int(counter.get(k, 0)) + 1

    @staticmethod
    def _normalize_http_path(path):
        raw = str(path or '/').strip() or '/'
        raw = raw.split('?', 1)[0] or '/'
        return raw if len(raw) <= 160 else (raw[:157] + '...')

    def _emit_http_stats_locked(self, minute_key, bucket, reason='minute_rollover'):
        total = int((bucket or {}).get('total', 0) or 0)
        if total <= 0:
            return
        path_map = (bucket or {}).get('paths', {}) if isinstance((bucket or {}).get('paths', {}), dict) else {}
        top_paths = sorted(path_map.items(), key=lambda item: item[1], reverse=True)[:8]
        os_log.info(
            'WEB_USER',
            'HTTP_STATS',
            'http request aggregate per minute',
            {
                'reason': str(reason or 'minute_rollover'),
                'minute_epoch': int(minute_key * 60),
                'total': total,
                'methods': dict((bucket or {}).get('methods', {})),
                'status': dict((bucket or {}).get('status', {})),
                'status_bands': dict((bucket or {}).get('status_bands', {})),
                'top_paths': top_paths,
            },
        )

    def record_http_request(self, method, path, status_code):
        with self._http_stats_lock:
            minute_now = int(time.time() // 60)
            if minute_now != self._http_stats_minute_key:
                self._emit_http_stats_locked(self._http_stats_minute_key, self._http_stats_bucket, reason='minute_rollover')
                self._http_stats_minute_key = minute_now
                self._http_stats_bucket = self._new_http_stats_bucket()

            bucket = self._http_stats_bucket
            bucket['total'] = int(bucket.get('total', 0) or 0) + 1
            self._inc_counter(bucket['methods'], str(method or 'UNKNOWN').upper())

            code = 0
            try:
                code = int(status_code or 0)
            except Exception:
                code = 0
            status_key = str(code) if code > 0 else 'unknown'
            band_key = (str(code // 100) + 'xx') if code > 0 else 'unknown'
            self._inc_counter(bucket['status'], status_key)
            self._inc_counter(bucket['status_bands'], band_key)
            self._inc_counter(bucket['paths'], self._normalize_http_path(path))

    def flush_http_stats(self, reason='manual'):
        with self._http_stats_lock:
            self._emit_http_stats_locked(self._http_stats_minute_key, self._http_stats_bucket, reason=reason)
            self._http_stats_minute_key = int(time.time() // 60)
            self._http_stats_bucket = self._new_http_stats_bucket()

    def _http_stats_snapshot(self):
        with self._http_stats_lock:
            bucket = self._http_stats_bucket or {}
            path_map = bucket.get('paths', {}) if isinstance(bucket.get('paths', {}), dict) else {}
            top_paths = sorted(path_map.items(), key=lambda item: item[1], reverse=True)[:8]
            return {
                'window_start_epoch': int(self._http_stats_minute_key * 60),
                'total': int(bucket.get('total', 0) or 0),
                'methods': dict(bucket.get('methods', {})),
                'status': dict(bucket.get('status', {})),
                'status_bands': dict(bucket.get('status_bands', {})),
                'top_paths': top_paths,
            }

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

    def _plugin_items(self):
        cfg = self._config_ref()
        service_plugins = (((cfg.get('RESOURCES', {}) or {}).get('service_plugins', {}) or {}))
        if not isinstance(service_plugins, dict):
            service_plugins = {}
        snap = self._service_snapshot()
        runtime = snap.get('runtime_index', {}) if isinstance(snap.get('runtime_index', {}), dict) else {}
        mounted = set(snap.get('mount_index', []) if isinstance(snap.get('mount_index', []), list) else [])
        items = []
        for name in sorted(service_plugins.keys()):
            item_cfg = service_plugins.get(name, {}) if isinstance(service_plugins.get(name, {}), dict) else {}
            rt = runtime.get(name, {}) if isinstance(runtime.get(name, {}), dict) else {}
            items.append({
                'name': name,
                'enabled': bool(item_cfg.get('enabled', True)),
                'mounted': name in mounted,
                'loaded': bool(rt.get('loaded', False)),
                'mode': str(item_cfg.get('mode', 'manual')),
            })
        return items

    def _set_plugin_enabled(self, plugin_name, enabled):
        name = str(plugin_name or '').strip().lower().replace('-', '_')
        if not name:
            return False, 'plugin name is required'
        cfg = self._config_ref()
        resources = cfg.setdefault('RESOURCES', {})
        service_plugins = resources.setdefault('service_plugins', {})
        plugin_cfg = service_plugins.setdefault(name, {})
        plugin_cfg['enabled'] = bool(enabled)
        saver = getattr(self.node, '_save_config', None)
        if callable(saver):
            saver()
        return True, None

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

    def _transport_items(self):
        snap = self._transport_snapshot()
        items = []
        for layer, key in (('application', 'application_status'), ('transport', 'transport_status'), ('physical', 'physical_status')):
            mp = snap.get(key, {}) if isinstance(snap.get(key, {}), dict) else {}
            for name in sorted(mp.keys()):
                items.append({'name': str(name), 'layer': layer, 'enabled': bool(mp.get(name, False))})
        return items

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
        return _friendly_label(path)

    @staticmethod
    def _infer_value_type(value):
        return _infer_value_type(value)

    def _field_annotation(self, path):
        return _field_annotation(path, self.FIELD_ANNOTATIONS)

    def _flatten_option_fields(self, path, value, fields):
        _flatten_option_fields(path, value, fields, self._is_key_writable, self.FIELD_ANNOTATIONS)

    def _category_title(self, prefix):
        return _category_title(prefix)

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
            'http_stats': self._http_stats_snapshot(),
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
        handler.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        handler.send_header('Pragma', 'no-cache')
        handler.send_header('Expires', '0')
        handler.send_header('Content-Length', str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _text_response(self, handler, status_code, text, content_type='text/plain; charset=utf-8'):
        body = str(text).encode('utf-8')
        handler.send_response(status_code)
        handler.send_header('Content-Type', content_type)
        handler.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        handler.send_header('Pragma', 'no-cache')
        handler.send_header('Expires', '0')
        handler.send_header('Content-Length', str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def _template_path(self, name):
        return self._base_dir / 'src' / 'opensynaptic' / 'services' / 'web_user' / 'templates' / str(name)

    def _load_template_text(self, name, fallback=''):
        path = self._template_path(name)
        try:
            return path.read_text(encoding='utf-8')
        except Exception:
            return str(fallback or '')

    @staticmethod
    def _runtime_js():
        from pathlib import Path
        here = Path(__file__).resolve().parent
        target = here / 'templates' / 'runtime.js'
        try:
            return target.read_text(encoding='utf-8')
        except Exception:
            return "window.__OS_WEB_RUNTIME_LOADED = false;"

    @staticmethod
    def _frontend_html():
        from pathlib import Path
        here = Path(__file__).resolve().parent
        target = here / 'templates' / 'index.html'
        try:
            return target.read_text(encoding='utf-8')
        except Exception:
            return "<!doctype html><html><body><h3>web_user template missing: templates/index.html</h3></body></html>"

    def _handler_cls(self):
        from .handlers import create_handler
        return create_handler(self)

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
        self.flush_http_stats(reason='stop')
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

