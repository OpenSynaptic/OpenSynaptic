# web_user plugin

Web management entry for OpenSynaptic nodes (dashboard + plugin/transport/config controls + user management).

## Start from CLI

```powershell
python -u src/main.py web-user --cmd start -- --host 127.0.0.1 --port 8765 --block
```

or use the standalone script entrypoint:

```powershell
os-web --cmd start -- --host 127.0.0.1 --port 8765 --block
```

Open `http://127.0.0.1:8765/` for the built-in management page.

## API

- `GET /health`, `GET /api/health`
- `GET /api/dashboard`
- `GET /api/dashboard?sections=identity,transport`
- `GET /api/config?key=a.b.c`
- `PUT /api/config`
- `GET /api/ui/config`
- `PUT /api/ui/config`
- `GET /api/options/schema?only_writable=1`
- `PUT /api/options`  (batch updates: `{ "updates": [{"key","value","value_type"}] }`)
- `GET /api/oscli/jobs?id=<job_id>`
- `GET /api/oscli/jobs?limit=20`
- `GET /api/oscli/metrics`
- `POST /api/oscli/execute`  (payload: `{ "command": "plugin-test --suite component", "background": true }`)
- `GET /api/plugins`
- `POST /api/plugins`
- `GET /api/transport`
- `POST /api/transport`
- `GET /users`
- `POST /users`
- `PUT /users/{username}`
- `DELETE /users/{username}`

When `auth_enabled=true`, pass `X-Admin-Token: <admin_token>` on management API calls.
When `read_only=true`, all write actions are blocked.

UI options (`RESOURCES.service_plugins.web_user`):

- `ui_enabled`: enable/disable `/` management page
- `ui_theme`: `router-dark` or `router-light`
- `ui_layout`: currently `sidebar`
- `ui_refresh_seconds`: dashboard auto refresh interval
- `ui_compact`: compact row density toggle

The built-in "Auto Option Studio" uses `/api/options/schema` to auto-generate typed controls:

- `bool` -> true/false selector
- `int` / `float` -> numeric input
- `str` -> text input
- `json` -> JSON textarea

Fields are grouped into categories (Web plugin, transport switches, engine, lease policy) and include labels + descriptions.

The built-in "Command Console" provides a visual command window and executes OpenSynaptic CLI commands through `/api/oscli/execute`.

## Plugin commands

```powershell
python -u src/main.py web-user --cmd status
python -u src/main.py web-user --cmd dashboard
python -u src/main.py web-user --cmd cli -- --line "status"
python -u src/main.py web-user --cmd cli -- --line "plugin-test --suite component"
python -u src/main.py web-user --cmd options-schema -- --only-writable
python -u src/main.py web-user --cmd options-set -- --key engine_settings.precision --value 6 --type int
python -u src/main.py web-user --cmd options-apply -- --updates '[{"key":"RESOURCES.service_plugins.web_user.ui_compact","value":true,"value_type":"bool"}]'
python -u src/main.py web-user --cmd list
python -u src/main.py web-user --cmd add -- --username alice --role admin
python -u src/main.py web-user --cmd update -- --username alice --role user --disable
python -u src/main.py web-user --cmd delete -- --username alice
python -u src/main.py web-user --cmd stop

# standalone alias (after install):
os-web --cmd status
os-web --cmd options-schema -- --only-writable
```

