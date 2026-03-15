# OpenSynaptic Architecture

OpenSynaptic is a 2-N-2 IoT protocol stack that converts sensor readings into UCUM-normalized facts, compresses them, packs them as binary frames, and dispatches them through pluggable transport layers.

---

## End-to-End Pipeline

```text
sensors list
    -> OpenSynapticStandardizer.standardize()   # UCUM normalization
    -> OpenSynapticEngine.compress()            # Base62 compression
    -> OSVisualFusionEngine.run_engine()        # FULL/DIFF packet build
    -> OpenSynaptic.dispatch(medium="UDP")      # application/transport/physical send
```

### Stage Responsibilities

- `OpenSynapticStandardizer`: converts raw sensor tuples to a structured fact schema and resolves UCUM units.
- `OpenSynapticEngine`: encodes structured facts to compact Base62 payloads.
- `OSVisualFusionEngine`: wraps payloads into protocol packets (`FULL_PACKET` or `DIFF_PACKET`).
- `OpenSynaptic.dispatch`: sends packet bytes through the selected transporter.

---

## Core Runtime Components

| Component | File | Responsibility |
|---|---|---|
| `OpenSynaptic` | `src/opensynaptic/core/pycore/core.py` | Orchestrates startup, ID checks, pipeline, and dispatch |
| `OSHandshakeManager` | `src/opensynaptic/core/pycore/handshake.py` | CMD dispatch, ID negotiation, and time sync |
| `TransporterManager` | `src/opensynaptic/core/pycore/transporter_manager.py` | Discovers/loads enabled drivers across layers |
| `ServiceManager` | `src/opensynaptic/services/service_manager.py` | Mount/load lifecycle for internal service plugins |
| `IDAllocator` | `plugins/id_allocator.py` | Allocates and persists uint32 IDs |

---

## Device ID Lifecycle

1. Node starts with missing `assigned_id` or sentinel `4294967295` (`MAX_UINT32`).
2. Node calls `ensure_id(server_ip, server_port, device_meta)`.
3. Server replies with `CMD.ID_ASSIGN`.
4. Assigned ID is persisted to `Config.json`.
5. `transmit()` is blocked with `RuntimeError` until a valid ID exists.

---

## Transport Layering (Application / Transport / Physical)

OpenSynaptic manages transport in three explicit layers:

- Application layer: `src/opensynaptic/services/transporters/drivers/`
- Transport layer: `src/opensynaptic/core/transport_layer/protocols/`
- Physical layer: `src/opensynaptic/core/physical_layer/protocols/`

Enable maps in `Config.json`:

- `RESOURCES.application_status`
- `RESOURCES.transport_status`
- `RESOURCES.physical_status`

Compatibility mirror:

- `RESOURCES.transporters_status` remains as a merged legacy map for CLI/tools.

---

## Configuration as Single Source of Truth

`Config.json` controls startup behavior, pipeline switches, backend selection, transporter config, service plugin defaults, and security behavior.

High-impact keys:

- `assigned_id`
- `engine_settings.core_backend`
- `engine_settings.active_standardization`
- `engine_settings.active_compression`
- `engine_settings.active_collapse`
- `RESOURCES.*_status` and `RESOURCES.*_config`
- `RESOURCES.service_plugins`

See [`CONFIG_SCHEMA.md`](CONFIG_SCHEMA.md) for a complete schema reference.

---

## Plugin and Service Model

- Built-in service defaults are normalized and synced by `services/plugin_registry.py`.
- Alias normalization is applied (`web-user` -> `web_user`).
- Startup sync ensures missing plugin entries are created in `Config.json`.
- Plugin load lifecycle is coordinated by `ServiceManager`.

---

## Registry Sharding Strategy

Device records are sharded by zero-padded ID:

```text
data/device_registry/{id[0:2]}/{id[2:4]}/{aid}.json
```

Use `opensynaptic.utils.paths.get_registry_path(aid)` to derive file locations reliably.

---

## Native Components

Some performance-critical paths depend on native bindings:

- `Base62Codec` (`src/opensynaptic/utils/base62/base62.py`)
- security helpers loaded through `src/opensynaptic/utils/c/native_loader.py`

There is no Python fallback for these code paths.

