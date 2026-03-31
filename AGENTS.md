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
| `IDAllocator` | `plugins/id_allocator.py` | uint32 ID pool with adaptive lease policy, persisted to `data/id_allocation.json` |
| `TransporterManager` | `src/opensynaptic/core/pycore/transporter_manager.py` | Auto-discovers and lazy-loads transporters |
| `ServiceManager` | `src/opensynaptic/services/service_manager.py` | Mount/load lifecycle hub for internal services and plugins |
| `plugin_registry` helpers | `src/opensynaptic/services/plugin_registry.py` | Built-in plugin defaults + alias normalization (`web-user` → `web_user`) |

---

## Config.json – Single Source of Truth

`Config.json` at project root remains the template/SSOT for defaults and repo-local tooling.  
Runtime CLI/node sessions default to user config `~/.config/opensynaptic/Config.json` (`get_user_config_path()`), and bootstrap/migrate from project `Config.json` when needed.
`OSContext` (`utils/paths.py`) still auto-detects repo root by walking up from `__file__` until it finds project `Config.json`.

Critical keys:
- `assigned_id` – uint32 device ID; `4294967295` (MAX_UINT32) is the **sentinel for "unassigned"**
- `--config` omitted in CLI / `OpenSynaptic()` constructor – defaults to `~/.config/opensynaptic/Config.json`
- `security_settings.id_lease` – ID reuse/lease policy object (see below for sub-keys)
  - `offline_hold_days` – default hold period (translates to `base_lease_seconds`)
  - `base_lease_seconds` – base lease duration for newly assigned or re-touched IDs (default 2,592,000 = 30 days)
  - `min_lease_seconds` – minimum lease floor (default 0, meaning adaptive can reduce to zero)
  - `rate_window_seconds` – observation window for new device rate calculation (default 3600)
  - `high_rate_threshold_per_hour` – threshold to trigger adaptive shortening (default 60/hr)
  - `ultra_rate_threshold_per_hour` – threshold to trigger force-zero lease (default 180/hr)
  - `ultra_rate_sustain_seconds` – how long ultra rate must sustain before force-zero applies (default 600s)
  - `high_rate_min_factor` – multiplier applied when high rate detected (default 0.2, min 20% of base lease)
  - `adaptive_enabled` – enable/disable adaptive lease shortening (default `true`)
  - `ultra_force_release` – immediately expire offline IDs when ultra rate active (default `true`)
  - `metrics_emit_interval_seconds` – how often to emit lease metrics (default 5s)
- `RESOURCES.transporters_status` – legacy merged status map used by CLI/tools; keep lowercase keys
- `RESOURCES.application_status / transport_status / physical_status` – active enable maps for L7/L4/PHY loading
- `RESOURCES.application_config / transport_config / physical_config` – per-layer driver options passed into `send()` as `application_options` / `transport_options` / `physical_options`
- `RESOURCES.registry` – path to device registry dir (default `data/device_registry/`)
- `engine_settings.precision` – Base62 decimal precision (default 4)
- `engine_settings.core_backend` – active core plugin (`pycore` / `rscore`), with env override support via `OPENSYNAPTIC_CORE`
- `engine_settings.active_standardization / active_compression / active_collapse` – pipeline stage toggles
- `engine_settings.zero_copy_transport` – enables memoryview passthrough send path (`true` by default; set `false` for legacy byte materialization fallback)
- `RESOURCES.service_plugins.<plugin_name>` – extended plugin defaults including `tui`, `web_user`, `dependency_manager`, `env_guard`

---

## ID Lifecycle & Lease Management

**Basic Flow:**
1. New device starts with `assigned_id` absent or `4294967295` (unassigned sentinel).
2. Call `node.ensure_id(server_ip, server_port, device_meta)` – sends `CMD.ID_REQUEST (0x01)` via UDP.
3. Server responds `CMD.ID_ASSIGN (0x02)` via `IDAllocator.allocate_id(meta)`.
4. Device records `assigned_id` in `Config.json`; `transmit()` raises `RuntimeError` without a valid ID.

**ID Lease & Reuse Policy:**
- Device offline detected → ID marked `offline` state, lease countdown starts (`lease_expires_at = now + effective_lease_seconds`)
- Default lease: **30 days** (configurable `security_settings.id_lease.offline_hold_days`)
- When device re-connects with same stable key (MAC/serial/UUID) → ID reactivated, lease reset to base
- Expired ID automatically reclaimed, moved to `released` pool for new device reuse
- **New device rate adaptive control**: 
  - High rate (> `high_rate_threshold_per_hour`, default 60/hr) → lease shortened by factor `high_rate_min_factor` (default 0.2)
  - Ultra rate (> `ultra_rate_threshold_per_hour`, default 180/hr for `ultra_rate_sustain_seconds`, default 600s) → `force_zero_lease_active=true`, offline IDs expire immediately
- Config keys in `security_settings.id_lease` drive all lease logic; `IDAllocator` reads them at `__init__` and on each allocation
- Metrics (`new_device_rate_per_hour`, `effective_lease_seconds`, `ultra_rate_active`) published to optional `metrics_sink` callable every `metrics_emit_interval_seconds` (default 5s); lease metrics also flushed to `Config.json` every `metrics_flush_seconds` (default 10s)

**Documentation**: See `docs/ID_LEASE_SYSTEM.md` for comprehensive guide and `docs/ID_LEASE_CONFIG_REFERENCE.md` for configuration quick-start.

---

## Display API – Self-Discoverable Visualization

`src/opensynaptic/services/display_api.py` defines a standard interface for plugins to register custom display sections that can be auto-discovered and rendered by both `web_user` and `tui`:

- **DisplayProvider** (base class): plugins subclass this to define extraction + formatting logic
  - `extract_data(node=None, **kwargs)` – extract/prepare data for a section
  - `format_json(data)` – return JSON-serializable dict (default: pass-through)
  - `format_html(data)` – return HTML string for web rendering (default: basic table)
  - `format_text(data)` – return plain text for terminal (default: pretty-printed JSON)
- **DisplayRegistry** (global singleton): auto-discovered providers register themselves
  - `register_display_provider(provider)` – register a `DisplayProvider` instance
  - `get_display_registry()` – fetch the global registry
  - Providers can specify category (`core` / `plugin`), priority (0–100, higher = first), refresh interval
- **render_section(name)** – unified function to extract + format a named section (called by TUI/web_user)
- **Built-in providers** (`src/opensynaptic/services/builtin_display_providers.py`):
  - `IdentityDisplayProvider` – device ID, version, timestamp
  - `ConfigDisplayProvider` – configuration snapshot
  - `TransportDisplayProvider` – active transporters/drivers per layer
  - `PipelineDisplayProvider` – standardization, compression, collapse pipeline state
  - `PluginsDisplayProvider` – mounted service plugins + status
  - `DatabaseDisplayProvider` – registry/DB metadata
- Plugins (e.g., `test_plugin`) can register their own providers to display metrics/state in TUI/web_user without modifying core UI code

---

## Built-in Service Plugins

Beyond the core TUI and test plugins, several utility service plugins are mounted automatically on startup:

- **env_guard** (`src/opensynaptic/services/env_guard/main.py`) – environment monitoring & auto-remediation
  - Monitors error streams and auto-fixes common environment issues (missing dependencies, misconfigured paths)
  - Manages resource installation and command history
  - Thread-safe; runs error-monitoring and repair loops in background
  - CLI: `os-node env-guard {monitor, list, install}`
  - Config key: `RESOURCES.service_plugins.env_guard` with `enabled` / `mode` / `max_errors` / `auto_install`

- **dependency_manager** (`src/opensynaptic/services/dependency_manager/main.py`) – dependency checking & repair
  - Inspects Python environment and pyproject.toml/requirements.txt
  - Auto-detects missing packages; can install via pip or conda
  - Generates detailed dependency health reports
  - Thread-safe operation; integrates with Display API for status display
  - CLI: `os-node deps {check, doctor, sync, repair, install}`
  - Config key: `RESOURCES.service_plugins.dependency_manager` with `enabled` / `mode`

- **db_engine** (`src/opensynaptic/services/db_engine/main.py`) – SQL database export and management
  - Provides unified SQL export for OpenSynaptic facts via pluggable drivers
  - Drivers: `SQLite`, `MySQL`, `PostgreSQL` in `drivers/` subdirectory
  - All inserts use parameter binding (no SQL injection risk)
  - API: `connect()`, `export_fact()`, `export_many()`, `close()`
  - Config key: `storage.sql` with `dialect`, `driver` (connection parameters)
  - Integrates with Display API for database metadata display

- **port_forwarder** (`src/opensynaptic/services/port_forwarder/main.py`) – advanced packet routing
  - Intercepts `dispatch()` calls and routes packets based on configurable rules
  - Rule model: `from_protocol/port` → `to_protocol/host/port`
  - Supports hijacking dispatch path for protocol/port transformations
  - Mounts via `ServiceManager.mount('port_forwarder', plugin, config)`
  - Integrates with Display API for rule status and metrics

All service plugins implement the ServiceManager lifecycle contract:
- `__init__(node, **kwargs)` – initialization with node reference
- `get_required_config()` → dict – default configuration schema
- `auto_load()` – post-mount startup (called by ServiceManager.load())
- `close()` – cleanup and shutdown
- `get_cli_commands()` → dict – CLI subcommand handlers (optional)
- Thread-safe: all state changes guarded by internal locks

---

## Transporter Plugin System

Transporters are tiered across three layers, each using `LayeredProtocolManager`:

- **Application (L7)**: `src/opensynaptic/services/transporters/drivers/` → managed by `TransporterService`
  - Auto-discovery constrained to `TransporterService.APP_LAYER_DRIVERS` (currently `{'mqtt', 'matter', 'zigbee'}`)
  - To add a new app driver: add key to `APP_LAYER_DRIVERS`, create driver module, enable in `application_status` + configure in `application_config`
- **Transport (L4)**: `src/opensynaptic/core/transport_layer/protocols/` → managed by `TransportLayerManager`
  - Candidates: `udp`, `tcp`, `quic`, `iwip`, `uip` (tuple in `manager.py:_CANDIDATES`)
- **Physical (PHY)**: `src/opensynaptic/core/physical_layer/protocols/` → managed by `PhysicalLayerManager`
  - Candidates: `uart`, `rs485`, `can`, `lora`, `bluetooth` (tuple in `manager.py:_CANDIDATES`)

**Common patterns:**
- All drivers implement `send(payload: bytes, config: dict) -> bool` (optional `listen(config, callback)`)
- Enable/disable via **layer-specific** status maps: `application_status`, `transport_status`, `physical_status`
- Per-layer config in `application_config`, `transport_config`, `physical_config`
- Adding a new T/L4/PHY protocol: update layer `manager.py:_CANDIDATES` tuple(s), update `TransporterManager` protocol sets used by `_migrate_resource_maps()`, then add status/config entries in `Config.json`
- All transporter keys must be **lowercase** in status/config maps; `TransporterManager._migrate_resource_maps()` keeps the legacy `transporters_status` as a merged mirror

---

## Device Registry Sharding

Registry files live at:
```
data/device_registry/{id[0:2]}/{id[2:4]}/{aid}.json
```
where shard segments are derived from `str(aid).zfill(10)`.  
Helper: `from opensynaptic.utils import get_registry_path; get_registry_path(aid)`

---

## Performance Metrics & Monitoring

**Tail Latency Percentiles (test_plugin):**
- `avg_latency_ms` – mean latency across all packets
- `p95_latency_ms` – 95th percentile latency
- `p99_latency_ms` – 99th percentile latency (critical SLA metric)
- `p99_9_latency_ms` – 99.9th percentile latency
- `p99_99_latency_ms` – 99.99th percentile latency (extreme tail)
- `min_latency_ms`, `max_latency_ms` – bookend latencies

All latency fields are computed and aggregated by `src/opensynaptic/services/test_plugin/stress_tests.py` and available in CLI output via `--suite stress` and `--suite compare` runs.

**ID Lease Metrics:**
- `new_device_rate_per_hour` – rolling rate of new device allocations; drives adaptive lease shortening
- `effective_lease_seconds` – computed lease duration after applying adaptive policy
- `ultra_rate_active` – boolean flag indicating whether ultra-rate threshold is sustained
- `force_zero_lease_active` – boolean indicating whether offline IDs are being force-expired
- `total_reclaimed` – cumulative count of IDs reclaimed from expired leases
- Published by `IDAllocator._emit_metrics_nolock()` to optional `metrics_sink` callable every `metrics_emit_interval_seconds` (default 5s); lease metrics also flushed to `Config.json` every `metrics_flush_seconds` (default 10s)

---

## Unit Libraries

- `libraries/Units/` – UCUM unit definitions as JSON with `__METADATA__.OS_UNIT_SYMBOLS`.
- `libraries/harvester.py → SymbolHarvester.sync()` – merges all unit files into `libraries/OS_Symbols.json`.
- `OpenSynapticEngine` resolves its symbol table from `RESOURCES.prefixes` or `RESOURCES.symbols` in `Config.json`; keep that path aligned with the harvester output.
- **Run harvester after adding/editing any unit JSON** so `OpenSynapticEngine` picks up the new symbols.

---

## Hardware Drivers

Custom hardware-specific drivers live in `src/opensynaptic/hardware_drivers/`:

- **CAN_Driver** (`CAN.py`) – CAN bus segmentation & framing
  - Constructor: `CAN_Driver(can_id=291)` sets CAN ID and MTU (8 bytes)
  - `segment_send(payload)` – splits payload into CAN frames with header/DLC
  - Produces list of frame dicts: `{'id': can_id, 'dlc': len, 'data': chunk}`
  - Useful for integrating with L7 transporter for CAN-native dispatch

- **LoRa_Driver** (`LoRa.py`) – LoRa transceiver interface
  - Supports frequency selection, SF/BW/CR tuning, regional regulations
  - Integration with physical layer stack via `send(payload, config)`

- **RS485_Driver** (`RS485.py`) – RS485 serial protocol
  - Modbus-compatible segmentation; hardware flow control support
  - Integration with physical layer stack via `send(payload, config)`

These drivers are separate from the tiered transporter system (L7/L4/PHY) and are typically used for custom hardware integrations or specialized sensor interfaces.

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

**Receiver Runtime Performance Stats:**
- `ReceiverRuntime` (`src/opensynaptic/core/Receiver.py`) emits periodic performance statistics with default **60s** reporting cadence
- Override `report_interval_s` in constructor for shorter debug cadence: `ReceiverRuntime(report_interval_s=5.0)`
- Stats include packet count, throughput, error rates, and tail latencies

---

## Developer Workflows

**Install (editable):**
```bash
pip install -e .
```

**Run standalone integration smoke harness** (repo-local quick verification):
```bash
python scripts/integration_test.py
```

**Run protocol receive harness** (UDP default; supports TCP via `--protocol tcp`):
```bash
python scripts/udp_receive_test.py --protocol udp --host 127.0.0.1 --port 8080 --config Config.json
```

**Run built-in plugin test suites:**
```bash
python -u src/main.py plugin-test --suite component
python -u src/main.py plugin-test --suite stress --workers 8 --total 200
python -u src/main.py plugin-test --suite all --workers 8 --total 200
python -u src/main.py plugin-test --suite full_load --total 100000 --with-component
python -u src/main.py plugin-test --suite integration
python -u src/main.py plugin-test --suite audit
```

**Use one-flag test profiles (maps to stress/compare presets):**
```bash
python -u src/main.py plugin-test --profile quick
python -u src/main.py plugin-test --profile deep
python -u src/main.py plugin-test --profile record
```

**Run backend comparison / high-load profiling flows:**
```bash
python -u src/main.py plugin-test --suite compare --total 10000 --workers 8 --processes 2 --threads-per-process 4 --runs 2 --warmup 1
python -u src/main.py plugin-test --suite stress --auto-profile --profile-total 50000 --profile-runs 1 --final-runs 1 --profile-processes 1,2,4,8 --profile-threads 4,8,16 --profile-batches 32,64,128
```

**Switch Rust core backend:**
```bash
python -u src/main.py core --set rscore --persist
```

**Build Rust core (CLI):**
```bash
python -u src/main.py rscore-build
python -u src/main.py rscore-check
```

**Build Rust core (standalone script):**
```bash
python -u src/opensynaptic/core/rscore/build_rscore.py  # Compiles and installs os_rscore DLL
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
node = OpenSynaptic()           # defaults to ~/.config/opensynaptic/Config.json
node.ensure_id("192.168.1.100", 8080)
packet, aid, strategy = node.transmit(sensors=[["V1","OK", 3.14, ("Pa")]])
node.dispatch(packet, medium="UDP")
```

**Run driver capability audit script:**
```bash
python scripts/audit_driver_capabilities.py
```

---

## Key Conventions

**ServiceManager Plugin Lifecycle** (`src/opensynaptic/services/service_manager.py`):
- Plugins must implement: `__init__(node, **kwargs)`, `get_required_config()` (static), `auto_load()`
- Optional: `close()` (for cleanup), `get_cli_commands()` / `get_cli_completions()` (for CLI dispatch)
- Mount via `ServiceManager.mount(name, service_instance, config)` before calling `load(name)`
- `get_cli_commands()` should return `dict[sub_cmd: callable]` where each callable accepts argv and returns int (exit code)
- All state changes must be thread-safe; use internal `_lock` pattern for concurrent access
- Display Providers (subclass `DisplayProvider`) auto-register via `register_display_provider(instance)` and are discovered by TUI/web_user

**Display Provider Pattern** (for TUI/web_user visualization):
- Subclass `DisplayProvider` with `extract_data(node, **kwargs)` and optional format methods
- Register via `register_display_provider(provider)` or init-time registration in plugin `auto_load()`
- Each provider defines: `plugin_name`, `section_id`, `display_name`, `category`, `priority` (0–100), `refresh_interval_s`
- `render_section(name)` automatically discovers and calls the matching provider(s)
- Plugins can display arbitrary state without modifying web_user or tui UI code

**CLI Entry Points** (`pyproject.toml:[project.scripts]`):
- `os-node` – Interactive CLI with fallback to `run` daemon after idle timeout (managed by `src/opensynaptic/main.py:main()`)
- `os-cli` – Inline command execution; no REPL (entrypoint `opensynaptic.main:cli_entry`)
- `os-tui` – TUI dashboard (aliases to `os-cli tui`)
- `os-web` – Standalone web plugin entrypoint (maps to `web-user`; implemented by `src/opensynaptic/main.py:web_main`)
- **CLI structure**: all command parsers in `src/opensynaptic/CLI/parsers/` (modular by feature: `core`, `config`, `test`, `plugin`, `native`, `service`, `extra`); assembled by `build_parser()` in `build_parser.py`

**Core & Configuration:**
- **`config_path` is always normalized to absolute path** in `OpenSynaptic.__init__`; when omitted, default path is `~/.config/opensynaptic/Config.json`.
- Import core symbols from `opensynaptic.core` only; `src/opensynaptic/core/__init__.py` is the public facade and `get_core_manager()` selects the active core plugin (`pycore`).
- `plugins/` is outside `src/`; `core.py` adds the project root to `sys.path` if the import fails.
- `OSContext` (`ctx`) is a module-level singleton imported at `from opensynaptic.utils import ctx`; it is instantiated at import time.
- Core selection precedence is `OPENSYNAPTIC_CORE` env var → `engine_settings.core_backend` in `Config.json` → `pycore` default (`src/opensynaptic/core/coremanager.py`).
- `4294967295` / `MAX_UINT32` is treated as "unassigned" everywhere – never use it as a real device ID.
- Transporter keys in all status maps are **lowercase** (`"tcp"`, not `"TCP"`).
- `TransporterManager._migrate_resource_maps()` keeps `transporters_status` as a merged mirror of the three layer maps.
- Built-in plugin defaults are synced on node startup via `sync_all_plugin_defaults(self.config)` before transporters auto-load.
- Plugin auto-load on node startup is gated by `auto_start=True` (`autoload_enabled_plugins(..., auto_start_only=True)`); default plugin mode is manual unless config opts in.
- `Base62Codec` (`src/opensynaptic/utils/base62/base62.py`) and security helpers are native-only ctypes bindings loaded via `src/opensynaptic/utils/c/native_loader.py`; there is no Python fallback for those code paths.
- All `send()` paths converge on `to_wire_payload(...)` helper to avoid payload preparation duplication.
- `rscore` Python wrappers share FFI proxy pattern via `src/opensynaptic/core/rscore/_ffi_proxy.py` to minimize Rust interface boilerplate.

