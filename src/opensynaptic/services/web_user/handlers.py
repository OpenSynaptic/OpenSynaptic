from urllib.parse import parse_qs, urlparse


def create_handler(service):
    from http.server import BaseHTTPRequestHandler

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
                service._json_response(self, 200, {'ok': True, 'plugins': snap, 'items': service._plugin_items()})
                return
            if path == '/api/plugins/config':
                ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                if not ok:
                    service._json_response(self, code, {'error': err})
                    return
                plugin = str((query.get('plugin', [''])[0] or '')).strip()
                if not plugin:
                    service._json_response(self, 400, {'ok': False, 'error': 'plugin is required'})
                    return
                only_writable = str((query.get('only_writable', ['1'])[0] or '1')).strip().lower() in ('1', 'true', 'yes', 'on')
                schema = service.build_plugin_option_schema(plugin_name=plugin, only_writable=only_writable)
                service._json_response(self, 200, {'ok': True, 'plugin': plugin, 'schema': schema})
                return
            if path == '/api/plugins/commands':
                ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                if not ok:
                    service._json_response(self, code, {'error': err})
                    return
                plugin = str((query.get('plugin', [''])[0] or '')).strip()
                if not plugin:
                    service._json_response(self, 400, {'ok': False, 'error': 'plugin is required'})
                    return
                service._json_response(self, 200, service.get_plugin_commands_metadata(plugin))
                return
            if path == '/api/plugins/visual-schema':
                ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                if not ok:
                    service._json_response(self, code, {'error': err})
                    return
                plugin = str((query.get('plugin', [''])[0] or '')).strip()
                if not plugin:
                    service._json_response(self, 400, {'ok': False, 'error': 'plugin is required'})
                    return
                service._json_response(self, 200, service.get_plugin_visual_schema(plugin))
                return
            if path == '/api/transport':
                ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                if not ok:
                    service._json_response(self, code, {'error': err})
                    return
                service._json_response(self, 200, {'ok': True, 'transport': service._transport_snapshot(), 'items': service._transport_items()})
                return
            if path == '/api/display/providers':
                ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                if not ok:
                    service._json_response(self, code, {'error': err})
                    return
                service._json_response(self, 200, service.get_display_providers_metadata())
                return
            if path.startswith('/api/display/render/'):
                ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                if not ok:
                    service._json_response(self, code, {'error': err})
                    return
                section_path = path.split('/api/display/render/', 1)[1]
                fmt = str((query.get('format', ['json'])[0] or 'json')).strip().lower()
                output = service.render_display_section(section_path, fmt=fmt)
                service._json_response(self, 200 if output is not None else 404, output or {'error': 'section not found'})
                return
            if path == '/api/display/all':
                ok, code, err = service._authorize_request(self.headers, write=False, management=True)
                if not ok:
                    service._json_response(self, code, {'error': err})
                    return
                fmt = str((query.get('format', ['json'])[0] or 'json')).strip().lower()
                output = service.collect_all_display_sections(fmt=fmt)
                service._json_response(self, 200, output)
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
                if action == 'set_enabled':
                    enabled = bool(payload.get('enabled', True))
                    ok, err = service._set_plugin_enabled(plugin, enabled)
                    if not ok:
                        service._json_response(self, 400, {'ok': False, 'error': err, 'plugin': plugin})
                        return
                    service._json_response(self, 200, {'ok': True, 'plugin': plugin, 'enabled': enabled, 'items': service._plugin_items()})
                    return
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
            if path == '/api/plugins/config':
                ok, code, err = service._authorize_request(self.headers, write=True, management=True)
                if not ok:
                    service._json_response(self, code, {'error': err})
                    return
                payload = self._read_json()
                plugin = str(payload.get('plugin', '') or '').strip()
                if not plugin:
                    service._json_response(self, 400, {'ok': False, 'error': 'plugin is required'})
                    return
                ok, out = service.apply_plugin_option_updates(plugin_name=plugin, updates=payload.get('updates', []))
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
                import json
                return json.loads(raw.decode('utf-8'))
            except Exception:
                return {}

        def log_message(self, fmt, *args):
            try:
                status_code = args[1] if len(args) > 1 else None
                service.record_http_request(
                    method=getattr(self, 'command', 'UNKNOWN'),
                    path=getattr(self, 'path', '/'),
                    status_code=status_code,
                )
            except Exception:
                # Keep handler resilient even if stats aggregation hits unexpected input.
                return

    return _Handler

