# dependency_manager plugin

Provides dependency inspection and maintenance commands for OpenSynaptic.

## CLI usage

Via standalone command:

```powershell
python -u src/main.py deps --cmd check
python -u src/main.py deps --cmd doctor
python -u src/main.py deps --cmd repair
python -u src/main.py deps --cmd sync
python -u src/main.py deps --cmd install -- --name requests
```

Via generic plugin router:

```powershell
python -u src/main.py plugin-cmd --plugin dependency_manager --cmd check
```

## Notes

- `check` compares `pyproject.toml` declared dependencies with installed packages.
- `doctor` runs `pip check`.
- `repair` installs only missing dependencies.
- `sync` installs all declared dependencies.
- `install` installs a user-specified package.

