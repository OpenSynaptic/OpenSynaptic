# OpenSynaptic

**2-N-2 high-performance IoT protocol stack** — standardises sensor readings into UCUM units, compresses them via Base62 encoding, wraps them in a binary packet, and dispatches over pluggable transporters (TCP / UDP / UART / LoRa / MQTT / CAN).

## Try In 30 Seconds

```powershell
pip install -e .
os-node demo --open-browser
```

- Default user config path: `~/.config/opensynaptic/Config.json`
- First run launches onboarding wizard (`--yes` / `--no-wizard` supported)

### CLI Completion (Tab)

```powershell
py -3 -m pip install argcomplete
powershell -ExecutionPolicy Bypass -File .\scripts\enable_argcomplete.ps1
```

Manual (without script):

```powershell
Invoke-Expression (register-python-argcomplete os-node --shell powershell)
```

Restart PowerShell after activation.

![OpenSynaptic Demo Quickstart](https://raw.githubusercontent.com/OpenSynaptic/OpenSynaptic/main/docs/assets/demo_quickstart.svg)

---

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Install](#install)
- [Minimal Usage](#minimal-usage)
- [CLI Quick Reference](#cli-quick-reference)
- [Config.json](#configjson)
- [Testing](#testing)
- [v0.2.0 Performance Focus](#v020-performance-focus)
  - [Optimized Usage Examples](#optimized-usage-examples)
- [RS Core (rscore) Quick Start](#rs-core-rscore-quick-start)
- [Adding a Transporter](#adding-a-transporter)
- [API Reference](#api-reference)
- [Documentation Hub](#documentation-hub)
- [Release Notes](#release-notes)
- [Plugin Config Auto-Sync](#plugin-config-auto-sync)

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
src/opensynaptic/
├── core/
│   ├── __init__.py             # Public core facade + active backend loader
│   ├── pycore/
│   │   ├── core.py             # Orchestrator – OpenSynaptic class
│   │   ├── standardization.py  # UCUM normalisation
│   │   ├── solidity.py         # Base62 compress / decompress
│   │   ├── unified_parser.py   # Binary packet encode/decode, template learning
│   │   ├── handshake.py        # CMD byte dispatch, device ID negotiation
│   │   └── transporter_manager.py # Auto-discovers pluggable transporters
│   ├── rscore/                 # Rust core backend + build/check helpers
│   ├── transport_layer/        # L4 protocol managers and protocols/
│   ├── physical_layer/         # PHY protocol managers and protocols/
│   ├── layered_protocol_manager.py # 3-layer protocol orchestration
│   ├── coremanager.py          # Core selection/runtime manager
│   └── loader.py               # Core/plugin loader
├── services/
│   ├── service_manager.py      # Plugin mount / load / dispatch hub
│   ├── plugin_registry.py      # Built-in plugin mapping + config default sync
│   ├── tui/                    # Terminal UI service (section-aware, interactive)
│   ├── web_user/               # Lightweight web UI + user management API
│   ├── dependency_manager/     # Dependency check/repair/install plugin
│   ├── env_guard/              # Environment guard service
│   ├── transporters/           # Application-layer transporter service
│   ├── db_engine/              # Database integration service
│   └── test_plugin/            # Built-in component & stress test suite
├── utils/
│   ├── constants.py            # LogMsg enum, MESSAGES, CLI_HELP_TABLE
│   ├── logger.py               # os_log singleton
│   ├── paths.py                # OSContext, read_json, write_json, get_registry_path
│   ├── base62/                 # Base62 codec bindings/utilities
│   ├── security/               # crc/xor/session-key helpers
│   └── c/                      # Native loader/build helpers
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
print(manager.available_cores())             # e.g. ['pycore', 'rscore']
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
| `core` | Show/switch core backend (`pycore` / `rscore`) |
| `transporter-toggle` | Enable or disable a transporter in Config |
| `plugin-list` | List mounted service plugins |
| `plugin-load` | Load a mounted plugin by name |
| `plugin-cmd` | Route a sub-command to a plugin's CLI handler |
| `plugin-test` | Run component or stress tests |
| `native-check` | Check native compiler/toolchain availability |
| `native-build` | Build native C bindings (optionally include RS core) |
| `rscore-build` | Build and install Rust RS core shared library |
| `rscore-check` | Check RS core DLL/runtime readiness and active core |
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
| `RESOURCES.transporters_status` | map | `{}` | Legacy merged compatibility map (mirrors layer-specific status maps) |
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

## Packaging And Release

```powershell
# Build and validate Python distributions
py -3 -m pip install -e .[dev]
py -3 -m build
py -3 -m twine check dist/*

# Build Rust acceleration wheel (maturin)
py -3 -m maturin build --manifest-path src/opensynaptic/core/rscore/rust/Cargo.toml --release
```

GitHub Actions workflows are defined in `.github/workflows/ci.yml` and `.github/workflows/release.yml`.
Configure repository secrets `TEST_PYPI_API_TOKEN` and `PYPI_API_TOKEN` before tag-based publishing.

---

## v0.2.0 Performance Focus

This release line emphasizes practical performance tuning and backend acceleration:

- Multi-process stress controls: `--processes`, `--threads-per-process`, `--batch-size`
- Auto-tuning profile scan: `--auto-profile` with `--profile-processes`, `--profile-threads`, `--profile-batches`
- RS core workflow: `rscore-build`, `rscore-check`, `core --set rscore --persist`
- Backend comparison flow: `plugin-test --suite compare`

Detailed release note -> [`docs/releases/v0.2.0.md`](docs/releases/v0.2.0.md)

### Optimized Usage Examples

```powershell
# High-throughput multi-process stress
python -u src/main.py plugin-test --suite stress --total 20000 --workers 16 --processes 4 --threads-per-process 4 --batch-size 64

# Auto-profile best concurrency matrix
python -u src/main.py plugin-test --suite stress --auto-profile --profile-total 50000 --profile-runs 1 --final-runs 1 --profile-processes 1,2,4,8 --profile-threads 4,8,16 --profile-batches 32,64,128

# Build/check/switch to RS core
python -u src/main.py rscore-build
python -u src/main.py rscore-check
python -u src/main.py core --set rscore --persist

# Compare pycore vs rscore performance
python -u src/main.py plugin-test --suite compare --total 10000 --workers 8 --processes 2 --threads-per-process 4 --runs 2 --warmup 1
```

---

## RS Core (rscore) Quick Start

Use this flow to build, verify, and switch to the Rust core backend.

```powershell
# 1) Build RS core shared library
python -u src/main.py rscore-build

# 2) Verify runtime status (DLL path/load state, active core)
python -u src/main.py rscore-check

# 3) Switch backend for current process + persist in Config.json
python -u src/main.py core --set rscore --persist

# 4) Optional: enforce RS path in stress tests
python -u src/main.py plugin-test --suite stress --total 5000 --workers 8 --processes 2 --require-rust
```

If you need to keep Python backend, switch back with:

```powershell
python -u src/main.py core --set pycore --persist
```

More details: [`docs/RSCORE_API.md`](docs/RSCORE_API.md), [`docs/PYCORE_RUST_API.md`](docs/PYCORE_RUST_API.md), [`docs/releases/v0.2.0.md`](docs/releases/v0.2.0.md)

---

## Adding a Transporter

See [`docs/TRANSPORTER_PLUGIN.md`](docs/TRANSPORTER_PLUGIN.md).

---

## API Reference

See [`docs/API.md`](docs/API.md).

Core facade and loader reference -> [`docs/CORE_API.md`](docs/CORE_API.md)

---

## Documentation Hub

- Repository docs map: [`docs/INDEX.md`](docs/INDEX.md)
- Start here: [`docs/README.md`](docs/README.md)
- Architecture walkthrough: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Config schema: [`docs/CONFIG_SCHEMA.md`](docs/CONFIG_SCHEMA.md)
- Transporter/plugin extension: [`docs/TRANSPORTER_PLUGIN.md`](docs/TRANSPORTER_PLUGIN.md)
- Core internals: [`docs/internal/PYCORE_INTERNALS.md`](docs/internal/PYCORE_INTERNALS.md)
- Rust core references: [`docs/RSCORE_API.md`](docs/RSCORE_API.md), [`docs/PYCORE_RUST_API.md`](docs/PYCORE_RUST_API.md)
- Upgrade guide: [`docs/guides/upgrade/v0.3.0.md`](docs/guides/upgrade/v0.3.0.md)
- Driver quick reference: [`docs/guides/drivers/quick-reference.md`](docs/guides/drivers/quick-reference.md)
- Version comparison report: [`docs/reports/releases/v0.2.0-v0.3.0-comparison.md`](docs/reports/releases/v0.2.0-v0.3.0-comparison.md)
- Release summary: [`docs/releases/announcement-summary-v0.3.0.md`](docs/releases/announcement-summary-v0.3.0.md)

---

## Release Notes

- Project changelog: [`CHANGELOG.md`](CHANGELOG.md)
- v0.2.0 draft archive: [`docs/releases/v0.2.0.md`](docs/releases/v0.2.0.md)
- v0.3.0 announcement: [`docs/releases/v0.3.0_announcement.md`](docs/releases/v0.3.0_announcement.md)

## Plugin Config Auto-Sync

Built-in plugin settings are stored in `Config.json` at:

`RESOURCES.service_plugins.<plugin_name>`

These entries are auto-created with defaults if missing; plugins remain manual-start and do not auto-run at process startup.
