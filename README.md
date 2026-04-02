# OpenSynaptic

**2-N-2 high-performance IoT protocol stack** — standardises sensor readings into UCUM units, compresses them via Base62 encoding, wraps them in a binary packet, and dispatches over pluggable transporters (TCP / UDP / UART / LoRa / MQTT / CAN).

## Try In 30 Seconds

```powershell
pip install -e .
os-node demo --open-browser
```

Windows (no `Activate.ps1` required):

```powershell
.\run-main.cmd demo --open-browser
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
- [Why OpenSynaptic?](#why-opensynaptic)
- [Performance at a Glance](#performance-at-a-glance)
- [Use Cases](#use-cases)
- [Minimal Usage](#minimal-usage)
- [CLI Quick Reference](#cli-quick-reference)
- [Config.json](#configjson)
- [Testing](#testing)
- [Native And Rust Build](#native-and-rust-build)
- [Adding a Transporter](#adding-a-transporter)
- [API Reference](#api-reference)
- [Documentation Hub](#documentation-hub)
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
├── integration_test.py
├── udp_receive_test.py
├── audit_driver_capabilities.py
├── services_smoke_check.py
└── cli_exhaustive_check.py
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

### Windows PowerShell Startup Note

If you see this error when activating a virtual environment:

```text
Activate.ps1 cannot be loaded because running scripts is disabled on this system.
```

Use the project wrappers and run without activation:

```powershell
.\scripts\venv-python.cmd -m pip install -e .
.\scripts\venv-python.cmd -m pytest tests/unit tests/integration -q
.\scripts\venv-python.cmd -u src/main.py --help
.\run-main.cmd --help
```

If you need activation in the current shell only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& ".\.venv\Scripts\Activate.ps1"
```

### First-Run Native Auto Repair

On first run, OpenSynaptic now auto-attempts native C binding repair if required runtime libraries are missing.

- Trigger point: first run startup preflight and node initialization failure fallback.
- What it does: runs the same native build pipeline as `native-build`, then retries node startup once.
- If compiler/toolchain is missing, it returns structured guidance and records environment hints through `env_guard`.

Disable this behavior only when needed:

```powershell
$env:OPENSYNAPTIC_AUTO_NATIVE_REPAIR = "0"
```

---

## Why OpenSynaptic?

| Feature | MQTT + JSON | CoAP | OpenSynaptic |
|---------|-------------|------|--------------|
| Data Standardization | ❌ | ❌ | ✅ UCUM |
| Compression | ❌ | ❌ | ✅ Base62 + DIFF |
| Transport Flexibility | TCP only | UDP only | ✅ Pluggable (TCP/UDP/LoRa/CAN/MQTT) |
| Latency (end-to-end) | 1-5 ms | 1-5 ms | **9.7 μs** |
| Throughput (single core) | ~10k ops/s | ~10k ops/s | **1.14M ops/s** |

---

## ⚡ Performance at a Glance

<div align="center">

![Throughput](https://img.shields.io/badge/Throughput-1.10M%2B%20ops%2Fs-0A7E07?style=for-the-badge)
![P99 Latency](https://img.shields.io/badge/P99-0.0250%20ms-1E40AF?style=for-the-badge)
![Stability](https://img.shields.io/badge/Stress-20M%20ops%20%7C%200%20failures-7C3AED?style=for-the-badge)

</div>

<table>
  <tr>
    <td><strong>Total Ops</strong><br/>20,000,000</td>
    <td><strong>Success</strong><br/>20,000,000</td>
    <td><strong>Failed</strong><br/>0</td>
    <td><strong>Elapsed</strong><br/>18.185 s</td>
  </tr>
  <tr>
    <td><strong>Throughput</strong><br/>1,099,812.5 ops/s</td>
    <td><strong>Avg</strong><br/>0.0097 ms</td>
    <td><strong>P95</strong><br/>0.0155 ms</td>
    <td><strong>P99</strong><br/>0.0250 ms</td>
  </tr>
  <tr>
    <td><strong>P99.9</strong><br/>0.0546 ms</td>
    <td><strong>P99.99</strong><br/>0.1146 ms</td>
    <td><strong>Min</strong><br/>0.0042 ms</td>
    <td><strong>Max</strong><br/>0.1388 ms</td>
  </tr>
</table>

### Run Profile

| Field | Value |
|---|---:|
| Core Backend | `rscore` |
| Execution Mode | `hybrid` |
| Chain Mode | `e2e_loopback` |
| Processes | `8` |
| Threads per Process | `2` |
| Batch Size | `258` |

### Stage Timing Breakdown (ms)

| Stage | Avg | P95 | P99 | P99.9 | P99.99 | Min | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| `standardize_ms` | 0.0032 | 0.0052 | 0.0083 | 0.0182 | 0.0382 | 0.0014 | 0.0463 |
| `compress_ms` | 0.0032 | 0.0052 | 0.0083 | 0.0182 | 0.0382 | 0.0014 | 0.0463 |
| `fuse_ms` | 0.0032 | 0.0052 | 0.0083 | 0.0182 | 0.0382 | 0.0014 | 0.0463 |

📊 [Full Benchmark Report](docs/reports/PERFORMANCE_OPTIMIZATION_REPORT.md)

---

## 💡 Use Cases

### Smart Agriculture (Offline)
Deploy a $30 SBC as a local cloud, aggregating data from LoRa sensors. No internet required.

### Industrial IoT (Unified)
Replace multiple proprietary protocols with a single OpenSynaptic stack, reducing integration cost by 50%.

### Privacy-First Smart Home
Keep all sensor data on a local SBC; control via mobile app without exposing data to public cloud.

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

All commands are available via `os-node` (installed entrypoint), `./run-main.cmd` (Windows), or `python -u src/main.py`:

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
# Windows shortcut (no Activate.ps1 needed)
.\run-main.cmd plugin-test --suite component

# Component tests
python -u src/main.py plugin-test --suite component

# Stress test
python -u src/main.py plugin-test --suite stress --workers 8 --total 200

# Web UI (foreground mode)
python -u src/main.py web-user --cmd start -- --host 127.0.0.1 --port 8765 --block

# Dependency checks and repair
python -u src/main.py deps --cmd check
python -u src/main.py deps --cmd repair

# Both suites
python -u src/main.py plugin-test --suite all

# Local integration and capability checks
python scripts/integration_test.py
python scripts/udp_receive_test.py --protocol udp --host 127.0.0.1 --port 8080 --config Config.json
python scripts/audit_driver_capabilities.py
python scripts/services_smoke_check.py
```

---

## Native And Rust Build

```powershell
# Windows shortcut (no Activate.ps1 needed)
.\run-main.cmd native-check
.\run-main.cmd native-build

python -u src/main.py native-check
python -u src/main.py native-build
python -u src/main.py rscore-build
python -u src/main.py rscore-check
python -u src/main.py core --set rscore --persist
```

If needed, switch back:

```powershell
python -u src/main.py core --set pycore --persist
```

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
- ID lease docs: [`docs/ID_LEASE_SYSTEM.md`](docs/ID_LEASE_SYSTEM.md), [`docs/ID_LEASE_CONFIG_REFERENCE.md`](docs/ID_LEASE_CONFIG_REFERENCE.md)

---

## Plugin Config Auto-Sync

Built-in plugin settings are stored in `Config.json` at:

`RESOURCES.service_plugins.<plugin_name>`

These entries are auto-created with defaults if missing; plugins remain manual-start and do not auto-run at process
