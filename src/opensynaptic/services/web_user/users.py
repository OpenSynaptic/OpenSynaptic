import json
import threading
import time
from pathlib import Path

from opensynaptic.utils import os_log


class UserStore:
    def __init__(self, data_file):
        self._data_file = Path(data_file)
        self._lock = threading.RLock()
        self._users = {'users': []}
        self.load()

    def load(self):
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

    def save(self):
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
            self.save()
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
            self.save()
            return True, None

    def delete_user(self, username):
        with self._lock:
            users = self._users.get('users', [])
            before = len(users)
            users = [u for u in users if str(u.get('username', '')).lower() != str(username).lower()]
            if len(users) == before:
                return False, 'user not found'
            self._users['users'] = users
            self.save()
            return True, None

