# OpenSynaptic – AI Agent Guide

## Project Overview
OpenSynaptic is a **2-N-2 high-performance IoT protocol stack** (description: `pyproject.toml`).  
It standardises sensor readings into UCUM units, compresses them via Base62 encoding, wraps them in a binary packet, and dispatches over pluggable transporters (TCP/UDP/UART/LoRa/MQTT/CAN…).

---

## Architecture: Core Pipeline

```
sensors list
    → OpenSynapticStandardizer.standardize()   # UCUM normalisation
    → OpenSynapticEngine.compress()            # Base62 solidity compression
    → OSVisualFusionEngine.run_engine()        # binary packet (FULL / DIFF strategy)
    → OpenSynaptic.dispatch(medium="UDP")      # physical send via transporter
```

**Key classes and files:**

| Class | File | Role |
|---|---|---|
| `OpenSynaptic` | `src/opensynaptic/core/pycore/core.py` | Orchestrator – compose all subsystems |
| `CoreManager` | `src/opensynaptic/core/coremanager.py` | Discovers/lazy-loads core plugins (`pycore` / `rscore`) and resolves facade symbols |
| `OpenSynapticStandardizer` | `src/opensynaptic/core/pycore/standardization.py` | Sensor → UCUM fact normalisation |
| `OpenSynapticEngine` | `src/opensynaptic/core/pycore/solidity.py` | Base62 compress / decompress |
| `OSVisualFusionEngine` | `src/opensynaptic/core/pycore/unified_parser.py` | Binary packet encode/decode, template learning |
| `OSHandshakeManager` | `src/opensynaptic/core/pycore/handshake.py` | CMD byte dispatch; device ID negotiation |
| `IDAllocator` | `plugins/id_allocator.py` | uint32 ID pool, persisted to `data/id_allocation.json` |
| `TransporterManager` | `src/opensynaptic/core/pycore/transporter_manager.py` | Auto-discovers and lazy-loads transporters |
| `ServiceManager` | `src/opensynaptic/services/service_manager.py` | Mount/load lifecycle hub for internal services and plugins |
| `plugin_registry` helpers | `src/opensynaptic/services/plugin_registry.py` | Built-in plugin defaults + alias normalization (`web-user` → `web_user`) |

---

## Config.json – Single Source of Truth

`Config.json` at project root drives **all** runtime behaviour.  
`OSContext` (`utils/paths.py`) auto-detects root by walking up from `__file__` until it finds `Config.json`.

Critical keys:
- `assigned_id` – uint32 device ID; `4294967295` (MAX_UINT32) is the **sentinel for "unassigned"**
- `RESOURCES.transporters_status` – legacy merged status map used by CLI/tools; keep lowercase keys
- `RESOURCES.application_status / transport_status / physical_status` – active enable maps for L7/L4/PHY loading
- `RESOURCES.application_config / transport_config / physical_config` – per-layer driver options passed into `send()` as `application_options` / `transport_options` / `physical_options`
- `RESOURCES.registry` – path to device registry dir (default `data/device_registry/`)
- `engine_settings.precision` – Base62 decimal precision (default 4)
- `engine_settings.core_backend` – active core plugin (`pycore` / `rscore`), with env override support via `OPENSYNAPTIC_CORE`
- `engine_settings.active_standardization / active_compression / active_collapse` – pipeline stage toggles
- `engine_settings.zero_copy_transport` – enables memoryview passthrough send path (`true` by default; set `false` for legacy byte materialization fallback)
- `RESOURCES.service_plugins.<plugin_name>` – plugin runtime defaults auto-synced from `services/plugin_registry.py`

---

## ID Lifecycle

1. New device starts with `assigned_id` absent or `4294967295`.
2. Call `node.ensure_id(server_ip, server_port, device_meta)` – sends `CMD.ID_REQUEST (0x01)` via UDP.
3. Server responds `CMD.ID_ASSIGN (0x02)`; `assigned_id` is persisted back into `Config.json`.
4. `transmit()` raises `RuntimeError` if called without a valid `assigned_id`.

---

## Transporter Plugin System

- Transporters are tiered now:
  - Application: `src/opensynaptic/services/transporters/drivers/` (managed by `TransporterService`)
  - Transport: `src/opensynaptic/core/transport_layer/protocols/` (managed by `TransportLayerManager`)
  - Physical: `src/opensynaptic/core/physical_layer/protocols/` (managed by `PhysicalLayerManager`)
- Drivers still implement `send(payload: bytes, config: dict) -> bool` (optional `listen(config, callback)`).
- Enable protocols in the **layer-specific** status map (`application_status`, `transport_status`, `physical_status`).
- Application auto-discovery is constrained to `TransporterService.APP_LAYER_DRIVERS`; adding a new app driver requires adding its key there.
- Transport/physical discovery iterates manager candidate tuples (`_CANDIDATES` in each manager); adding a new protocol requires updating candidates + status/config entries.
- Current transport candidate keys are `udp`, `tcp`, `quic`, `iwip`, `uip` (`src/opensynaptic/core/transport_layer/manager.py`); keep config keys exactly lowercase.

---

## Device Registry Sharding

Registry files live at:
```
data/device_registry/{id[0:2]}/{id[2:4]}/{aid}.json
```
where shard segments are derived from `str(aid).zfill(10)`.  
Helper: `from opensynaptic.utils import get_registry_path; get_registry_path(aid)`

---

## Unit Libraries

- `libraries/Units/` – UCUM unit definitions as JSON with `__METADATA__.OS_UNIT_SYMBOLS`.
- `libraries/harvester.py → SymbolHarvester.sync()` – merges all unit files into `libraries/OS_Symbols.json`.
- `OpenSynapticEngine` resolves its symbol table from `RESOURCES.prefixes` or `RESOURCES.symbols` in `Config.json`; keep that path aligned with the harvester output.
- **Run harvester after adding/editing any unit JSON** so `OpenSynapticEngine` picks up the new symbols.

---

## Logging Convention

Use the `os_log` singleton (`from opensynaptic.utils import os_log`):

```python
os_log.err("MODULE_ID", "EVENT_ID", exception, {"context": "dict"})
os_log.info("STD", "UNIT", "resolved kg", {"raw": "kilogram"})
os_log.log_with_const("info", LogMsg.READY, root=self.base_dir)
```

All user-facing message templates are in `utils/constants.py:MESSAGES`.  
Add new `LogMsg` enum members there before using them with `log_with_const`.

---

## Developer Workflows

**Install (editable):**
```bash
pip install -e .
```

**Run concurrency smoke test** (validates transmit/receive under load):
```bash
python scripts/concurrency_smoke.py [total=200] [workers=8] [sources=6]
```

**Run built-in plugin test suites:**
```bash
python -u src/main.py plugin-test --suite component
python -u src/main.py plugin-test --suite stress --workers 8 --total 200
python -u src/main.py plugin-test --suite all --workers 8 --total 200
```

**Run backend comparison / high-load profiling flows:**
```bash
python -u src/main.py plugin-test --suite compare --total 10000 --workers 8 --processes 2 --threads-per-process 4 --runs 2 --warmup 1
python -u src/main.py plugin-test --suite stress --auto-profile --profile-total 50000 --profile-runs 1 --final-runs 1 --profile-processes 1,2,4,8 --profile-threads 4,8,16 --profile-batches 32,64,128
```

**Build/check/switch Rust core backend:**
```bash
python -u src/main.py rscore-build
python -u src/main.py rscore-check
python -u src/main.py core --set rscore --persist
```

**Run zero-copy closeout harness:**
```bash
python -u scripts/zero_copy_closeout.py --runs 3 --total 100000 --config Config.json
```

**Check/build native bindings** (required for Base62 + security code paths):
```bash
python -u src/main.py native-check
python -u src/main.py native-build
```

**Sync unit symbol table after editing `libraries/Units/`:**
```python
from libraries.harvester import SymbolHarvester
SymbolHarvester().sync()
```

**Minimal node usage (see bottom of `src/opensynaptic/core/pycore/core.py`):**
```python
node = OpenSynaptic()           # reads Config.json via ctx auto-detection
node.ensure_id("192.168.1.100", 8080)
packet, aid, strategy = node.transmit(sensors=[["V1","OK", 3.14, ("Pa")]])
node.dispatch(packet, medium="UDP")
```

---

## Key Conventions

- **`config_path` always passed as absolute path** – all subsystems receive it from `OpenSynaptic.__init__` to avoid CWD-relative path bugs.
- Import core symbols from `opensynaptic.core` only; `src/opensynaptic/core/__init__.py` is the public facade and `get_core_manager()` selects the active core plugin (`pycore`).
- `plugins/` is outside `src/`; `core.py` adds the project root to `sys.path` if the import fails.
- `OSContext` (`ctx`) is a module-level singleton imported at `from opensynaptic.utils import ctx`; it is instantiated at import time.
- Core selection precedence is `OPENSYNAPTIC_CORE` env var → `engine_settings.core_backend` in `Config.json` → `pycore` default (`src/opensynaptic/core/coremanager.py`).
- `4294967295` / `MAX_UINT32` is treated as "unassigned" everywhere – never use it as a real device ID.
- Transporter keys in all status maps are **lowercase** (`"tcp"`, not `"TCP"`).
- `TransporterManager._migrate_resource_maps()` keeps `transporters_status` as a merged mirror of the three layer maps.
- Built-in plugin defaults are synced on node startup via `sync_all_plugin_defaults(self.config)` before transporters auto-load.
- `Base62Codec` (`src/opensynaptic/utils/base62/base62.py`) and security helpers are native-only ctypes bindings loaded via `src/opensynaptic/utils/c/native_loader.py`; there is no Python fallback for those code paths.

