# OpenSynaptic CLI and TUI

All commands are available via `os-node` (installed entry-point) or `python -u src/main.py`.

---

## Command Reference

| Command | Aliases | Description |
|---|---|---|
| `run` | `os-run` | Persistent run loop; maintains protocol heartbeat until Ctrl+C or `--duration` |
| `snapshot` | `os-snapshot` | Print node / service / transporter JSON snapshot |
| `receive` | `os-receive` | Start UDP receiver (server-side packet ingestion loop) |
| `demo` | `os-demo` | One-command localhost onboarding: virtual sensors + Web UI |
| `tui` | `os-tui` | Render a TUI snapshot; add `--interactive` for live mode |
| `time-sync` | `os-time-sync` | Synchronise clock with the server once |
| `ensure-id` | `os-ensure-id` | Request a device ID from the server and persist it to `Config.json` |
| `transmit` | `os-transmit` | Encode one sensor reading and dispatch via transporter |
| `inject` | `os-inject` | Push sensor data through pipeline stages and print intermediate output |
| `decode` | `os-decode` | Decode a binary packet (hex) or Base62 string back to readable JSON |
| `watch` | `os-watch` | Real-time poll a module's state (Ctrl+C or `--duration` to stop) |
| `reload-protocol` | `os-reload-protocol` | Invalidate and reload one protocol adapter |
| `config-show` | `os-config-show` | Display `Config.json` or one top-level section |
| `config-get` | `os-config-get` | Read a dot-notation key path from `Config.json` |
| `config-set` | `os-config-set` | Write a typed value to a dot-notation key path |
| `wizard` | `init`, `os-wizard`, `os-init` | Interactive config generator (`--default` for one-shot defaults) |
| `repair-config` | `os-repair-config` | Repair/bootstrap `~/.config/opensynaptic/Config.json` for loopback mode |
| `transporter-toggle` | `os-transporter-toggle` | Enable or disable a transporter entry in `Config.json` |
| `plugin-list` | `os-plugin-list` | List all mounted service plugins and their runtime state |
| `plugin-load` | `os-plugin-load` | Load a mounted plugin by name (calls `auto_load()`) |
| `plugin-cmd` | `os-plugin-cmd` | Route a sub-command to a plugin's own CLI handler |
| `plugin-test` | `os-plugin-test` | Run component tests, stress tests, or both |
| `native-check` | `os-native-check` | Check native compiler environment and selected toolchain |
| `native-build` | `os-native-build` | Build native C bindings with real-time progress and timeout guards |
| `env-guard` | `os-env-guard` | Environment guard plugin status/control and local JSON resource/status files |
| `web-user` | `os-web-user` | Standalone CLI entry for web_user plugin |
| `deps` | `os-deps` | Standalone CLI entry for dependency_manager plugin |
| `transport-status` | `os-transport-status` | Show application / transport / physical layer states |
| `db-status` | `os-db-status` | Show DB engine enabled status and dialect |
| `help` | `os-help` | Print full help |

---

## Examples

```powershell
# ── Basic node operations ───────────────────────────────────────────────────
python -u src/main.py demo              --open-browser
python -u src/main.py demo              --temp-config --once
python -u src/main.py wizard
python -u src/main.py init --default
python -u src/main.py repair-config
python -u src/main.py snapshot          --config Config.json
python -u src/main.py ensure-id         --config Config.json --host 127.0.0.1 --port 8080
python -u src/main.py transmit          --config Config.json --sensor-id V1 --value 3.14 --unit Pa --medium UDP
python -u src/main.py reload-protocol   --config Config.json --medium udp
python -u src/main.py run               --config Config.json --interval 5
python -u src/main.py run               --config Config.json --once

# ── TUI ─────────────────────────────────────────────────────────────────────
python -u src/main.py tui               --config Config.json
python -u src/main.py tui               --config Config.json --section transport
python -u src/main.py tui               --config Config.json --interactive --interval 2.0
python -u src/main.py tui               --config Config.json --interactive --section pipeline --interval 1.0

# ── Config editing ───────────────────────────────────────────────────────────
python -u src/main.py config-show       --config Config.json
python -u src/main.py config-show       --config Config.json --section engine_settings
python -u src/main.py config-get        --config Config.json --key engine_settings.precision
python -u src/main.py config-get        --config Config.json --key RESOURCES.transporters_status
python -u src/main.py config-set        --config Config.json --key engine_settings.precision --value 6 --type int
python -u src/main.py config-set        --config Config.json --key security_settings.drop_on_crc16_failure --value false --type bool
python -u src/main.py config-set        --config Config.json --key storage.sql.driver.path --value "data/my.db"
# Write a whole sub-object (--type json)
python -u src/main.py config-set        --config Config.json --key RESOURCES.transport_config.quic --value '{"port":4433,"timeout":3.0}' --type json

# ── Transporter toggle ───────────────────────────────────────────────────────
python -u src/main.py transporter-toggle --config Config.json --name udp  --enable
python -u src/main.py transporter-toggle --config Config.json --name lora --disable

# ── inject – run sensor data through a specific pipeline stage ───────────────
python -u src/main.py inject --config Config.json --module standardize --sensor-id V1 --value 3.14 --unit Pa
python -u src/main.py inject --config Config.json --module compress    --sensor-id T1 --value 25.0 --unit Cel
python -u src/main.py inject --config Config.json --module fuse        --sensor-id P1 --value 101325 --unit Pa
python -u src/main.py inject --config Config.json --module full        --sensor-id V1 --value 3.14 --unit Pa
# Multi-sensor via JSON array
python -u src/main.py inject --config Config.json --module full --sensors '[["V1","OK",3.14,"Pa"],["T1","OK",25.0,"Cel"]]'
# Multi-sensor via JSON file (PowerShell / Windows friendly)
'[["V1","OK",3.14,"Pa"],["T1","OK",25.0,"Cel"]]' | Out-File -Encoding utf8 sensors.json
python -u src/main.py inject --config Config.json --module full --sensors-file sensors.json

# ── decode ───────────────────────────────────────────────────────────────────
python -u src/main.py decode --config Config.json --format hex --data "3f010000000a..."
python -u src/main.py decode --config Config.json --format b62 --data "HUB_01.1.AAAA|V1>1.P:abc|"

# ── watch – real-time monitor (Ctrl+C to stop) ───────────────────────────────
python -u src/main.py watch --config Config.json --module config    --interval 2
python -u src/main.py watch --config Config.json --module registry  --interval 5
python -u src/main.py watch --config Config.json --module transport --interval 3
python -u src/main.py watch --config Config.json --module pipeline  --interval 1 --duration 30

# ── Plugin commands ──────────────────────────────────────────────────────────
python -u src/main.py plugin-list --config Config.json
python -u src/main.py plugin-load --config Config.json --name tui
# Route a sub-command to the TUI plugin's own handler
python -u src/main.py plugin-cmd --config Config.json --plugin tui --cmd render
python -u src/main.py plugin-cmd --config Config.json --plugin tui --cmd render -- --section transport
python -u src/main.py plugin-cmd --config Config.json --plugin tui --cmd interactive -- --interval 2.0
# Route a sub-command to the test_plugin
python -u src/main.py plugin-cmd --config Config.json --plugin test_plugin --cmd component
python -u src/main.py plugin-cmd --config Config.json --plugin test_plugin --cmd stress -- --total 100 --workers 4
# Direct web_user command
python -u src/main.py web-user --config Config.json --cmd start -- --host 127.0.0.1 --port 8765 --block
# Direct dependency manager command
python -u src/main.py deps --config Config.json --cmd check
python -u src/main.py deps --config Config.json --cmd repair
# Environment guard command
python -u src/main.py env-guard --config Config.json --cmd status
python -u src/main.py env-guard --config Config.json --cmd set -- --auto-install true
python -u src/main.py env-guard --config Config.json --cmd resource-show
python -u src/main.py env-guard --config Config.json --cmd resource-init

# ── Testing ───────────────────────────────────────────────────────────────────
python -u src/main.py plugin-test --config Config.json --suite component
python -u src/main.py plugin-test --config Config.json --suite stress  --workers 8 --total 200
python -u src/main.py plugin-test --config Config.json --suite all     --workers 8 --total 200

# ── Native precheck / build (timeout-safe) ───────────────────────────────────
python -u src/main.py native-check
python -u src/main.py native-check --json
python -u src/main.py native-check --timeout 5
python -u src/main.py native-build
python -u src/main.py native-build --idle-timeout 5 --max-timeout 30
python -u src/main.py native-build --no-progress --json
```

---

## `inject` – Module Options

| `--module` | Stops after | Output keys |
|---|---|---|
| `standardize` | Standardizer | `standardize` (fact dict with UCUM-normalised values) |
| `compress` | Engine | `standardize` + `compress` (Base62 string) |
| `fuse` / `full` | Fusion Engine | all above + `fuse` → `{hex, length}` |

---

## `watch` – Module Options

| `--module` | What is monitored |
|---|---|
| `config` | Top-level `Config.json` scalars + key sub-dicts |
| `registry` | Device registry file modification timestamps |
| `transport` | Active transporters list + `transporters_status` map |
| `pipeline` | Standardizer cache size, Engine symbol count, Fusion template count |

---

## `tui` – Section Options

| `--section` | Contents |
|---|---|
| `identity` | `device_id`, `assigned_id`, `VERSION` |
| `config` | `engine_settings`, `payload_switches`, `OpenSynaptic_Setting`, `security_settings` |
| `transport` | Active transporters + all three status maps |
| `pipeline` | Standardizer cache, Engine rev-unit table, Fusion template count |
| `plugins` | `ServiceManager` mount and runtime indexes |
| `db` | DB engine enabled flag and dialect |

Omit `--section` to render all sections at once.  
Add `--interactive` to enter the live-refresh loop.

---

## `config-set` – Type Options

| `--type` | Example `--value` | Python result |
|---|---|---|
| `str` (default) | `"hello"` | `"hello"` |
| `int` | `"6"` | `6` |
| `float` | `"3.14"` | `3.14` |
| `bool` | `"true"` / `"false"` | `True` / `False` |
| `json` | `'{"a":1}'` | `{"a": 1}` |

---

## Global Flags

| Flag | Default | Description |
|---|---|---|
| `--config` | auto-detect | Absolute or relative path to `Config.json` |
| `--quiet` | `false` | Suppress INFO logs; only WARNING/ERROR pass through |
| `--interval` | `5.0` | `run` mode polling interval (seconds) |
| `--duration` | `0.0` | `run` / `watch` duration limit (seconds); `0` = unlimited |
| `--once` | `false` | `run` mode: execute one cycle then exit |
| `--yes` | `false` | First-run wizard: auto-start `demo` without prompt |
| `--no-wizard` | `false` | Skip first-run wizard prompt |

---

## Argcomplete Setup (Tab Completion)

```powershell
py -3 -m pip install argcomplete
powershell -ExecutionPolicy Bypass -File .\scripts\enable_argcomplete.ps1
```

Manual activation:

```powershell
Invoke-Expression (register-python-argcomplete os-node --shell powershell)
```

After restart, completion is available for:

- command names and subcommands
- `config-get --key` / `config-set --key` (nested dot paths + list indexes)
- transporter names on `--medium` / `--name`
- `plugin-cmd --plugin` and plugin `--cmd`

`config-* --key` completion uses a short-lived cache keyed by config file mtime to avoid repeated deep traversal on large files.

---

## Notes

- CLI and TUI both route logging through `opensynaptic.utils.os_log`.
- `TUIService` is mounted as a `ServiceManager` plugin under the name `"tui"`.
- `inject` does **not** require a valid `assigned_id`; it falls back to `0` for the fuse stage.
- `inject --sensors` takes a JSON array; on PowerShell use `--sensors-file <path>` to avoid quote-stripping issues.
- `decode --format hex` accepts `aabbcc`, `aa:bb:cc`, or `aa bb cc` (separators are stripped automatically).
- `config-set` with `--type json` writes entire sub-dicts in one command.
- `plugin-cmd` resolves plugins through `services/plugin_registry.py`; no plugin starts automatically on node boot.
- Plugins can expose `get_cli_completions()` to provide `plugin-cmd --cmd` completion metadata (fallback: `get_cli_commands()` keys).
- Required plugin settings are auto-added to `Config.json` under `RESOURCES.service_plugins.<plugin_name>`.
- `web-user --cmd start -- --block` keeps the process in foreground so the browser UI stays available.
