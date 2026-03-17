# web_user plugin

Lightweight web service for user management.

## Start from CLI

```powershell
python -u src/main.py web-user --cmd start -- --host 127.0.0.1 --port 8765 --block
```

Open `http://127.0.0.1:8765/` for the built-in management page.

## API

- `GET /health`
- `GET /users`
- `POST /users`
- `PUT /users/{username}`
- `DELETE /users/{username}`

## Plugin commands

```powershell
python -u src/main.py web-user --cmd status
python -u src/main.py web-user --cmd list
python -u src/main.py web-user --cmd add -- --username alice --role admin
python -u src/main.py web-user --cmd update -- --username alice --role user --disable
python -u src/main.py web-user --cmd delete -- --username alice
python -u src/main.py web-user --cmd stop
```

