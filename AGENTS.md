# OpenSynaptic – AI Agent Guide

## Project Overview
OpenSynaptic is a **2-N-2 high-performance IoT protocol stack** (描述: `pyproject.toml`).  
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
| `OpenSynaptic` | `src/opensynaptic/core/core.py` | Orchestrator – compose all subsystems |
| `OpenSynapticStandardizer` | `core/standardization.py` | Sensor → UCUM fact normalisation |
| `OpenSynapticEngine` | `core/solidity.py` | Base62 compress / decompress |
| `OSVisualFusionEngine` | `core/unified_parser.py` | Binary packet encode/decode, template learning |
| `OSHandshakeManager` | `core/handshake.py` | CMD byte dispatch; device ID negotiation |
| `IDAllocator` | `plugins/id_allocator.py` | uint32 ID pool, persisted to `data/id_allocation.json` |
| `TransporterManager` | `core/transporter_manager.py` | Auto-discovers and lazy-loads transporters |

---

## Config.json – Single Source of Truth

`Config.json` at project root drives **all** runtime behaviour.  
`OSContext` (`utils/paths.py`) auto-detects root by walking up from `__file__` until it finds `Config.json`.

Critical keys:
- `assigned_id` – uint32 device ID; `4294967295` (MAX_UINT32) is the **sentinel for "unassigned"**
- `RESOURCES.transporters_status` – map of `<transporter_name>: true/false`; `TransporterManager` reads this on startup and writes new keys automatically
- `RESOURCES.registry` – path to device registry dir (default `data/device_registry/`)
- `engine_settings.precision` – Base62 decimal precision (default 4)
- `engine_settings.active_standardization / active_compression / active_collapse` – pipeline stage toggles

---

## ID Lifecycle

1. New device starts with `assigned_id` absent or `4294967295`.
2. Call `node.ensure_id(server_ip, server_port, device_meta)` – sends `CMD.ID_REQUEST (0x01)` via UDP.
3. Server responds `CMD.ID_ASSIGN (0x02)`; `assigned_id` is persisted back into `Config.json`.
4. `transmit()` raises `RuntimeError` if called without a valid `assigned_id`.

---

## Transporter Plugin System

- Each `.py` in `src/opensynaptic/transporters/` is auto-discovered via `pkgutil`.
- A transporter must expose `send(payload: bytes, config: dict) -> bool` (and optionally `listen(config, callback)`).
- Enable a transporter: set its lowercase name to `true` in `Config.json → RESOURCES.transporters_status`.
- New files are **automatically registered as `false`** on first boot; no manual config edit required.

---

## Device Registry Sharding

Registry files live at:
```
data/device_registry/{id[0:2]}/{id[2:4]}/{id}.json
```
where `id` is zero-padded to 10 digits.  
Helper: `from opensynaptic.utils.paths import get_registry_path; get_registry_path(aid)`

---

## Unit Libraries

- `libraries/Units/` – UCUM unit definitions as JSON with `__METADATA__.OS_UNIT_SYMBOLS`.
- `libraries/harvester.py → SymbolHarvester.sync()` – merges all unit files into `libraries/OS_Symbols.json`.
- **Run harvester after adding/editing any unit JSON** so `OpenSynapticEngine` picks up the new symbols.

---

## Logging Convention

Use the `os_log` singleton (`from opensynaptic.utils.logger import os_log`):

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

**Sync unit symbol table after editing `libraries/Units/`:**
```python
from libraries.harvester import SymbolHarvester
SymbolHarvester().sync()
```

**Minimal node usage (see bottom of `core.py`):**
```python
node = OpenSynaptic()           # reads Config.json via ctx auto-detection
node.ensure_id("192.168.1.100", 8080)
packet, aid, strategy = node.transmit(sensors=[["V1","OK", 3.14, ("Pa")]])
node.dispatch(packet, medium="UDP")
```

---

## Key Conventions

- **`config_path` always passed as absolute path** – all subsystems receive it from `OpenSynaptic.__init__` to avoid CWD-relative path bugs.
- `plugins/` is outside `src/`; `core.py` adds the project root to `sys.path` if the import fails.
- `OSContext` (`ctx`) is a module-level singleton imported at `from opensynaptic.utils.paths import ctx`; it is instantiated at import time.
- `4294967295` / `MAX_UINT32` is treated as "unassigned" everywhere – never use it as a real device ID.
- Transporter keys in `transporters_status` are **lowercase** (`"tcp"`, not `"TCP"`).

