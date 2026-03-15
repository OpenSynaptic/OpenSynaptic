# OpenSynaptic

**2-N-2 high-performance IoT protocol stack** — standardises sensor readings into UCUM units, compresses them via Base62 encoding, wraps them in a binary packet, and dispatches over pluggable transporters (TCP / UDP / UART / LoRa / MQTT / CAN).

---

## Architecture

```
sensors list
    → OpenSynapticStandardizer.standardize()   # UCUM normalisation
    → OpenSynapticEngine.compress()            # Base62 solidity compression
    → OSVisualFusionEngine.run_engine()        # binary packet (FULL / DIFF strategy)
    → OpenSynaptic.dispatch(medium="UDP")      # physical send via transporter
```

```
opensynaptic/
├── core/
│   ├── __init__.py             # Public core API export surface
│   └── pycore/
│       ├── core.py             # Orchestrator – OpenSynaptic class
│       ├── standardization.py  # UCUM normalisation
│       ├── solidity.py         # Base62 compress / decompress
│       ├── unified_parser.py   # Binary packet encode/decode, template learning
│       ├── handshake.py        # CMD byte dispatch, device ID negotiation
│       └── transporter_manager.py # Auto-discovers pluggable transporters
├── services/
│   ├── service_manager.py      # Plugin mount / load / dispatch hub
│   ├── plugin_registry.py       # Built-in plugin mapping + config default sync
│   ├── tui/                    # Terminal UI service (section-aware, interactive)
│   ├── web_user/               # Lightweight web UI + user management API
│   ├── dependency_manager/     # Dependency check/repair/install plugin
│   └── test_plugin/            # Built-in component & stress test suite
├── utils/
│   ├── constants.py            # LogMsg enum, MESSAGES, CLI_HELP_TABLE
│   ├── logger.py               # os_log singleton
│   ├── paths.py                # OSContext, read_json, write_json, get_registry_path
│   ├── base62.py               # Base62Codec (native-only ctypes binding)
│   └── security_core.py        # crc/xor/session-key helpers (native-only ctypes binding)
├── CLI/
│   └── app.py                  # Argparse CLI (os-node entrypoint)
plugins/
└── id_allocator.py             # uint32 ID pool, persisted to data/id_allocation.json
libraries/
└── Units/                      # UCUM unit definition JSON files
scripts/
└── concurrency_smoke.py        # Concurrent pipeline smoke test
Config.json                     # Single source of truth for all runtime settings
```

---

## Prerequisites

- Python 3.11+
- Optional: `mysql-connector-python`, `psycopg[binary]`, `aioquic` (see `pyproject.toml`)

---

## Install

```powershell
pip install -e .
```

---

## Minimal Usage

```python
from opensynaptic.core import OpenSynaptic

node = OpenSynaptic()                        # reads Config.json automatically
node.ensure_id("192.168.1.100", 8080)        # request device ID from server
packet, aid, strategy = node.transmit(sensors=[["V1", "OK", 3.14, "Pa"]])
node.dispatch(packet, medium="UDP")
```

```python
from opensynaptic.core import get_core_manager

manager = get_core_manager()
print(manager.available_cores())             # ['pycore']
manager.set_active_core('pycore')
OpenSynaptic = manager.get_symbol('OpenSynaptic')
```

---

## CLI Quick Reference

All commands are available via `os-node` (installed entrypoint) or `python -u src/main.py`:

| Command | Description |
|---|---|
| `run` | Persistent run loop with heartbeat |
| `snapshot` | Print node/service/transporter JSON snapshot |
| `ensure-id` | Request device ID from server |
| `transmit` | Encode one sensor reading and dispatch |
| `inject` | Push data through pipeline stages and inspect output |
| `decode` | Decode a binary packet (hex) or Base62 string back to JSON |
| `watch` | Real-time poll a module's state (config / registry / transport / pipeline) |
| `tui` | Render TUI snapshot (add `--interactive` for live mode) |
| `config-show` | Display Config.json or a specific section |
| `config-get` | Read a dot-notation key path from Config |
| `config-set` | Write a typed value to a Config key path |
| `transporter-toggle` | Enable or disable a transporter in Config |
| `plugin-list` | List mounted service plugins |
| `plugin-load` | Load a mounted plugin by name |
| `plugin-cmd` | Route a sub-command to a plugin's CLI handler |
| `plugin-test` | Run component or stress tests |
| `web-user` | Run web_user plugin directly from CLI |
| `deps` | Run dependency_manager plugin directly from CLI |
| `transport-status` | Show all transporter layer states |
| `db-status` | Show DB engine status |
| `help` | Print full help |

Full usage examples → [`src/opensynaptic/CLI/README.md`](src/opensynaptic/CLI/README.md)

---

## Config.json

`Config.json` at the project root is the single source of truth.  
Key fields:

| Key | Type | Default | Effect |
|---|---|---|---|
| `assigned_id` | uint32 | `4294967295` | Device ID; `4294967295` = unassigned |
| `engine_settings.precision` | int | `4` | Base62 decimal places |
| `engine_settings.active_standardization` | bool | `true` | Toggle UCUM normalisation stage |
| `engine_settings.active_compression` | bool | `true` | Toggle Base62 compression stage |
| `RESOURCES.transporters_status` | map | `{}` | Enable/disable each transporter |
| `security_settings.drop_on_crc16_failure` | bool | `true` | Drop packets with bad CRC |

Full schema → [`docs/CONFIG_SCHEMA.md`](docs/CONFIG_SCHEMA.md)

---

## Testing

```powershell
# Component tests (unit tests for each pipeline stage)
python -u src/main.py plugin-test --suite component

# Stress test (200 concurrent pipeline encode cycles)
python -u src/main.py plugin-test --suite stress --workers 8 --total 200

# Web UI (foreground mode)
python -u src/main.py web-user --cmd start -- --host 127.0.0.1 --port 8765 --block

# Dependency checks and repair
python -u src/main.py deps --cmd check
python -u src/main.py deps --cmd repair

# Both suites
python -u src/main.py plugin-test --suite all

# Standalone smoke test
python scripts/concurrency_smoke.py 200 8 6
```

---

## Adding a Transporter

See [`docs/TRANSPORTER_PLUGIN.md`](docs/TRANSPORTER_PLUGIN.md).

---

## API Reference

See [`docs/API.md`](docs/API.md).

Core facade and loader reference -> [`docs/CORE_API.md`](docs/CORE_API.md)

## Plugin Config Auto-Sync

Built-in plugin settings are stored in `Config.json` at:

`RESOURCES.service_plugins.<plugin_name>`

These entries are auto-created with defaults if missing; plugins remain manual-start and do not auto-run at process startup.

