import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from opensynaptic.utils.logger import os_log


class WebUserService:
    """Lightweight HTTP plugin for basic user management."""

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
        self._load_users()

    @staticmethod
    def get_required_config():
        return {
            'enabled': True,
            'mode': 'manual',
            'host': '127.0.0.1',
            'port': 8765,
            'auto_start': False,
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

    def _save_users(self):
        with self._lock:
            self._data_file.parent.mkdir(parents=True, exist_ok=True)
            self._data_file.write_text(json.dumps(self._users, indent=2, ensure_ascii=False), encoding='utf-8')

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

    @staticmethod
    def _frontend_html():
        return """<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <title>OpenSynaptic User Manager</title>
  <style>
    body { font-family: Consolas, monospace; margin: 18px; background: #111; color: #eee; }
    .card { border: 1px solid #444; padding: 12px; margin-bottom: 12px; }
    input, select, button { margin: 4px; padding: 6px; }
    button { cursor: pointer; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #333; padding: 6px; text-align: left; }
  </style>
</head>
<body>
  <h2>OpenSynaptic - User Manager</h2>
  <div class='card'>
    <input id='username' placeholder='username'>
    <input id='role' placeholder='role (user/admin)' value='user'>
    <button onclick='addUser()'>Add User</button>
    <button onclick='reloadUsers()'>Reload</button>
  </div>
  <div class='card'>
    <table>
      <thead><tr><th>User</th><th>Role</th><th>Enabled</th><th>Actions</th></tr></thead>
      <tbody id='users'></tbody>
    </table>
  </div>
  <script>
    async function api(path, method='GET', body=null) {
      const r = await fetch(path, {
        method,
        headers: {'Content-Type': 'application/json'},
        body: body ? JSON.stringify(body) : null
      });
      return await r.json();
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
            <button onclick="updateUser('${u.username}')">Update</button>
            <button onclick="delUser('${u.username}')">Delete</button>
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
    reloadUsers();
  </script>
</body>
</html>"""

    def _handler_cls(self):
        service = self

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                path = urlparse(self.path).path
                if path == '/':
                    service._html_response(self, 200, service._frontend_html())
                    return
                if path == '/health':
                    service._json_response(self, 200, {'ok': True, 'service': 'web_user'})
                    return
                if path == '/users':
                    service._json_response(self, 200, {'users': service.list_users()})
                    return
                service._json_response(self, 404, {'error': 'not found'})

            def do_POST(self):
                path = urlparse(self.path).path
                if path != '/users':
                    service._json_response(self, 404, {'error': 'not found'})
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

            def do_PUT(self):
                path = urlparse(self.path).path
                if not path.startswith('/users/'):
                    service._json_response(self, 404, {'error': 'not found'})
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

    def start(self, host='127.0.0.1', port=8765):
        with self._lock:
            if self._server is not None:
                return False
            server = ThreadingHTTPServer((host, int(port)), self._handler_cls())  # type: ignore[arg-type]
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._server = server
            self._thread = thread
            self._started_at = time.time()
            os_log.info('WEB_USER', 'START', 'web user service started', {'host': host, 'port': int(port)})
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
            'list': _list,
            'add': _add,
            'update': _update,
            'delete': _delete,
        }

