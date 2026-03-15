# env_guard plugin

`env_guard` listens to structured internal errors and tracks environment-missing issues.

## What it does

- subscribes to `os_log.err(...)` events
- captures `EnvironmentMissingError` items
- writes local JSON files for resource rules and runtime status
- optionally runs remediation commands (`install_commands`) when `auto_install=true`

## JSON status file

Default paths:

- `data/env_guard/resources.json`
- `data/env_guard/status.json`

The payload includes:

- `status_json_path`
- `resource_library_json_path`
- `resource_summary`
- `issues_total`
- `attempts_total`
- `issues[]`
- `attempts[]`

## CLI usage

```powershell
python -u src/main.py env-guard --cmd status
python -u src/main.py env-guard --cmd set -- --auto-install true
python -u src/main.py env-guard --cmd resource-show
python -u src/main.py env-guard --cmd resource-init
```

You can also route via generic plugin command:

```powershell
python -u src/main.py plugin-cmd --plugin env_guard --cmd status
```

