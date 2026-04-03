# OpenSynaptic API Reference

API and service contracts currently implemented in the repository.

> **Deep-dive references:**
> - [`internal/PYCORE_INTERNALS.md`](internal/PYCORE_INTERNALS.md) — complete method-level reference for every class in `pycore/` including data contracts, wire formats, and security internals
> - [`RSCORE_API.md`](RSCORE_API.md) — Rust core (`rscore/`) API design specification
> - [`CONFIG_SCHEMA.md`](CONFIG_SCHEMA.md) — `Config.json` schema reference
> - [`TRANSPORTER_PLUGIN.md`](TRANSPORTER_PLUGIN.md) — how to add new transporter drivers

---

## `OpenSynaptic` — `src/opensynaptic/core/pycore/core.py` (exported via `opensynaptic.core`)

The top-level orchestrator. Instantiating it wires all subsystems from `Config.json`.

### Constructor

```python
OpenSynaptic(config_path: str | None = None)
```

| Parameter | Type | Description |
|---|---|---|
| `config_path` | `str \| None` | Optional path to `Config.json` (absolute or relative). If `None`, `OSContext` auto-detects the project root and loads the default config. |

**Key attributes after init:**

| Attribute | Type | Description |
|---|---|---|
| `config` | `dict` | Loaded `Config.json` contents |
| `config_path` | `str` | Active config path used by the instance |
| `base_dir` | `str` | Project root directory |
| `assigned_id` | `int \| None` | Current device ID (`4294967295` = unassigned) |
| `device_id` | `str` | Human-readable device identifier |
| `standardizer` | `OpenSynapticStandardizer` | Normalisation subsystem |
| `engine` | `OpenSynapticEngine` | Base62 compression subsystem |
| `fusion` | `OSVisualFusionEngine` | Binary packet encode/decode subsystem |
| `protocol` | `OSHandshakeManager` | CMD dispatch and session manager |
| `id_allocator` | `IDAllocator` | Server-side ID pool manager |
| `transporter_manager` | `TransporterManager` | Pluggable transporter registry |
| `active_transporters` | `dict[str, driver]` | Currently enabled transporter drivers |
| `service_manager` | `ServiceManager` | Plugin mount / lifecycle manager |
| `db_manager` | `DatabaseManager \| None` | SQL engine (if configured) |

### Methods

#### `ensure_id(server_ip, server_port, device_meta=None, timeout=5.0) → bool`

Requests a `uint32` device ID from the server via UDP (`CMD.ID_REQUEST`).  
Persists the assigned ID back into `Config.json`.  
Returns `True` if an ID was successfully obtained or already present.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `server_ip` | `str` | required | Server hostname or IP |
| `server_port` | `int` | required | UDP server port |
| `device_meta` | `dict \| None` | `None` | Optional metadata sent with the request |
| `timeout` | `float` | `5.0` | Socket timeout in seconds |

#### `ensure_time(server_ip=None, server_port=None, timeout=3.0) → int | None`

Synchronises the local clock with the server's UNIX timestamp.  
Returns the server timestamp (int) or `None` on failure.

#### `transmit(sensors, device_id=None, device_status='ONLINE', **kwargs) → tuple[bytes, int, str]`

Full pipeline: standardise → compress → fuse into binary packet.  
Raises `RuntimeError` if `assigned_id` is unset.

| Parameter | Type | Description |
|---|---|---|
| `sensors` | `list[list]` | `[[sensor_id, status, value, unit], ...]` |
| `device_id` | `str \| None` | Override device identifier (defaults to `self.device_id`) |
| `device_status` | `str` | Device status string, e.g. `"ONLINE"` |

Returns `(binary_packet, assigned_id, strategy_label)` where `strategy_label` is `"FULL_PACKET"` or `"DIFF_PACKET"`.

#### `dispatch(packet, medium=None) → bool`

Send a binary packet via the named transporter.

| Parameter | Type | Description |
|---|---|---|
| `packet` | `bytes \| str` | Encoded packet; strings are UTF-8 encoded |
| `medium` | `str \| None` | Transporter key, e.g. `"UDP"`, `"UART"`. Falls back to `Config.OpenSynaptic_Setting.default_medium`. |

Returns `True` on success.

#### `receive(raw_bytes) → dict`

Decode a raw binary packet back to a fact dict (calls `fusion.decompress`).

#### `receive_via_protocol(raw_bytes, addr=None) → Any`

Full protocol-layer dispatch: parse CMD byte, route to handshake manager.

#### `dispatch_with_reply(packet, server_ip=None, server_port=None, timeout=3.0) -> bytes | None`

Send a packet via UDP and wait for a single reply.

#### `transmit_fast(sensors=None, device_id=None, device_status='ONLINE', **kwargs) -> tuple[bytes, int, str]`

Fast-path alias of `transmit()` in `pycore` (same semantics; `rscore` may override with fused FFI behavior).

#### `transmit_batch(batch_items, **kwargs) -> list[tuple[bytes, int, str]]`

Batch wrapper over `transmit_fast()`.

#### `relay(packet) -> bytes`

Pass-through relay helper that re-encodes via fusion logic.

### Internal Helpers (not part of stable public API)

#### `_save_config()`

Persist the current in-memory `self.config` dict back to `Config.json`.

#### `_is_id_missing() -> bool`

Returns `True` if `assigned_id` is absent, zero, or equal to `MAX_UINT32` (`4294967295`).

---

## `OpenSynapticStandardizer` — `core/pycore/standardization.py`

Normalises raw sensor readings into UCUM-tagged fact dicts.

### Constructor

```python
OpenSynapticStandardizer(config_path: str = 'Config.json')
```

### `standardize(device_id, device_status, sensors, **kwargs) → dict`

| Parameter | Type | Description |
|---|---|---|
| `device_id` | `str` | Device identifier |
| `device_status` | `str` | Status string, e.g. `"ONLINE"` |
| `sensors` | `list[list]` | `[[sensor_id, status, value, unit], ...]` |
| `t` | `int` (kwarg) | UNIX timestamp (auto-populated if omitted) |

Returns a fact dict ready for `OpenSynapticEngine.compress()`.

---

## `OpenSynapticEngine` — `core/pycore/solidity.py`

Base62 compress and decompress pipeline facts.

### Constructor

```python
OpenSynapticEngine(config_path: str | None = None)
```

### `compress(fact: dict) → str`

Converts a fact dict into a compact Base62-encoded string.

### `decompress(b62_str: str) → dict`

Reverses `compress()` back to a fact dict.

---

## `OSVisualFusionEngine` — `core/pycore/unified_parser.py`

Binary packet encoder/decoder with template learning for DIFF compression.

### Constructor

```python
OSVisualFusionEngine(config_path: str | None = None)
```

### `run_engine(raw_input_str, strategy='DIFF') → bytes`

Encode a `"<aid>;<b62_payload>"` string into a binary packet.

| Parameter | Type | Description |
|---|---|---|
| `raw_input_str` | `str` | `"{assigned_id};{compressed}"` |
| `strategy` | `str` | `"FULL"` or `"DIFF"` |

**Binary frame layout (single hop, N=1):**

```
[CMD:1][route_count:1][AID:4][TID:1][TS:6][BODY:L][CRC8:1][CRC16:2]
                                                                 total = 15+L bytes
```

- `CMD` — data command byte (see `CMD` class in `handshake.py`)
- `AID` — source device ID, big-endian uint32
- `TID` — template ID uint8 (zero-padded 2-digit decimal string cast to int)
- `TS` — 6 LSBs of millisecond timestamp (big-endian uint64 bytes [2..8])
- `BODY` — CMD-dependent (full UTF-8 payload / diff bitmask+deltas / empty)
- `CRC8` — CRC-8 (poly=0x07, init=0x00) over plaintext body
- `CRC16` — CRC-16/CCITT (poly=0x1021, init=0xFFFF) over frame minus last 2 bytes

### `decompress(raw_bytes: bytes) → dict`

Decode a binary packet back to a fact dict.

Returns the decoded `SensorFact` dict with an extra `__packet_meta__` key:

```python
{
    "__packet_meta__": {
        "cmd":              int,
        "base_cmd":         int,
        "secure":           bool,
        "source_aid":       int,
        "crc16_ok":         bool,
        "crc8_ok":          bool,
        "timestamp_raw":    int,   # milliseconds
        "tid":              str,
        "template_learned": bool,
    }
}
```

### Other Methods

| Method | Description |
|---|---|
| `_set_local_id(id)` | Internal helper to update local device ID (used by core sync flow) |
| `relay(packet)` | Pass-through re-encode (relay node use case) |

---

## `OSHandshakeManager` — `core/pycore/handshake.py`

CMD byte dispatch, device session management, ID and time negotiation.

### Constructor

```python
OSHandshakeManager(target_sync_count=3, registry_dir=None, expire_seconds=86400, secure_store_path=None)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `target_sync_count` | `int` | `3` | Successful sends required before switching to DIFF strategy |
| `registry_dir` | `str \| None` | `None` | Device registry root directory |
| `expire_seconds` | `int` | `86400` | Session and sync-status entry TTL in seconds |
| `secure_store_path` | `str \| None` | `None` | Optional secure session persistence path |

### CMD Byte Constants (`CMD` class)

| Constant | Value | Description |
|---|---|---|
| `DATA_FULL` | 0x3F | Full payload (template + data) |
| `DATA_FULL_SEC` | 0x40 | Full payload, XOR-encrypted |
| `DATA_DIFF` | 0xAA | Differential update (changed slots only) |
| `DATA_DIFF_SEC` | 0xAB | Differential, XOR-encrypted |
| `DATA_HEART` | 0x7F | Heartbeat (no value change) |
| `DATA_HEART_SEC` | 0x80 | Heartbeat, XOR-encrypted |
| `ID_REQUEST` | 0x01 | Node requests a device ID |
| `ID_ASSIGN` | 0x02 | Server assigns a device ID |
| `ID_POOL_REQ` | 0x03 | Node requests a batch of IDs |
| `ID_POOL_RES` | 0x04 | Server batch ID assignment |
| `HANDSHAKE_ACK` | 0x05 | Positive acknowledgement |
| `HANDSHAKE_NACK` | 0x06 | Negative acknowledgement |
| `PING` | 0x09 | Liveness probe |
| `PONG` | 0x0A | Liveness reply |
| `TIME_REQUEST` | 0x0B | Node requests server timestamp |
| `TIME_RESPONSE` | 0x0C | Server returns UNIX timestamp |
| `SECURE_DICT_READY` | 0x0D | Server confirms key exchange |
| `SECURE_CHANNEL_ACK` | 0x0E | Node acknowledges encrypted channel |

### Strategy Methods

| Method | Returns | Description |
|---|---|---|
| `get_strategy(src_aid, has_template)` | `str` | Returns `"FULL_PACKET"` or `"DIFF_PACKET"` |
| `commit_success(src_aid)` | `None` | Increment successful send counter |

### Session Security Methods

| Method | Returns | Description |
|---|---|---|
| `note_local_plaintext_sent(aid, timestamp_raw, addr=None)` | `dict` | Derive pending session key from `(aid, timestamp_raw)` |
| `establish_remote_plaintext(aid, timestamp_raw, addr=None)` | `dict` | Server-side key derivation + set `dict_ready=True` |
| `confirm_secure_dict(aid, timestamp_raw=None, addr=None)` | `bool` | Promote pending key to active key |
| `mark_secure_channel(aid, addr=None)` | `dict` | Set `decrypt_confirmed=True`, state -> `"SECURE"` |
| `has_secure_dict(aid)` | `bool` | True if `dict_ready` flag is set |
| `should_encrypt_outbound(aid)` | `bool` | True if session has both `dict_ready` and `key` |
| `get_session_key(aid)` | `bytes | None` | Return XOR session key bytes |
| `note_server_time(ts)` | `None` | Record server timestamp for clock correction |

### Control Packet Builders

| Method | Returns | Description |
|---|---|---|
| `build_id_request(device_meta=None)` | `bytes` | `[0x01][seq:2][json_meta]` |
| `build_id_pool_request(count=10, meta=None)` | `bytes` | `[0x03][seq:2][count:2][json_meta]` |
| `build_ping()` | `bytes` | `[0x09][seq:2]` |
| `build_time_request()` | `bytes` | `[0x0B][seq:2]` |

### Transport-Level Handshake Loops

| Method | Returns | Description |
|---|---|---|
| `request_id_via_transport(transport_send_fn, transport_recv_fn, device_meta=None, timeout=5.0)` | `int | None` | Client-side ID request handshake |
| `request_id_pool_via_transport(transport_send_fn, transport_recv_fn, count=10, meta=None, timeout=5.0)` | `list[int]` | Client-side bulk ID request |
| `request_time_via_transport(transport_send_fn, transport_recv_fn, timeout=3.0)` | `int | None` | Client-side time sync handshake |
| `classify_and_dispatch(raw_bytes, addr=None)` | `dict` | Parse CMD byte and route to handler |

---

## `IDAllocator` — `plugins/id_allocator.py`

Thread-safe `uint32` ID pool with JSON persistence.

### Constructor

```python
IDAllocator(base_dir=None, start_id=1, end_id=4294967295,
            persist_file="data/id_allocation.json", max_released=10000,
            lease_policy=None, metrics_sink=None)
```

### Methods

| Method | Returns | Description |
|---|---|---|
| `allocate_id(meta=None)` | `int` | Allocate the next available ID |
| `allocate_pool(count, meta=None)` | `list[int]` | Allocate `count` IDs at once |
| `release_id(id_val, immediate=False)` | `bool` | Mark ID offline and reclaim immediately or after lease |
| `release_pool(ids)` | `int` | Bulk release; returns count released |
| `is_allocated(id_val)` | `bool` | Check if ID is in use |
| `get_meta(id_val)` | `dict` | Retrieve metadata stored at allocation time |
| `stats()` | `dict` | Includes allocator totals plus `lease_policy` and `lease_metrics` |

---

## `TransporterManager` — `core/pycore/transporter_manager.py`

Auto-discovers transporter driver modules from `services/transporters/` and the physical/transport layers.

### Constructor

```python
TransporterManager(master: OpenSynaptic)
```

### Key Methods

| Method | Returns | Description |
|---|---|---|
| `auto_load()` | `dict` | Discover and activate all enabled transporters |
| `get_driver(medium)` | `driver \| None` | Return the driver for a medium key |
| `refresh_protocol(medium)` | `driver \| None` | Invalidate cache and reload one driver |
| `runtime_tick()` | `bool` | Periodic heartbeat; reloads stale drivers |

---

## `CoreManager` — `core/coremanager.py`

Discovers and lazy-loads core plugins (for example `pycore` and `rscore`) and resolves the public `opensynaptic.core` symbols.

### Constructor

```python
CoreManager(base_package: str = 'opensynaptic.core', default_core: str = 'pycore')
```

### Key Methods

| Method | Returns | Description |
|---|---|---|
| `discover_cores()` | `list[str]` | Discover available core plugin packages under `opensynaptic.core.*` |
| `available_cores()` | `list[str]` | Return registered core plugin names |
| `set_config(config)` | `dict` | Set in-memory config for backend selection |
| `set_config_path(config_path)` | `dict` | Load Config and cache it for selection |
| `set_active_core(name)` | `str` | Force the active core plugin |
| `get_active_core_name()` | `str` | Return selected core plugin name |
| `load_core(name=None)` | `dict` | Load a core plugin manifest lazily |
| `list_symbols(name=None)` | `list[str]` | Return exported symbols for the selected core |
| `get_symbol(symbol_name, name=None)` | `Any` | Resolve one exported symbol from the selected core |
| `create_node(config_path=None, name=None)` | `OpenSynaptic` | Instantiate the selected core's `OpenSynaptic` class |

Top-level helper:

```python
from opensynaptic.core import get_core_manager
```

---

## `ServiceManager` — `services/service_manager.py`

Generic plugin mount / load / lifecycle hub.

### Constructor

```python
ServiceManager(config: dict | None = None, mode: str = 'runtime')
```

### Methods

| Method | Returns | Description |
|---|---|---|
| `mount(name, service, config=None, mode=None)` | `service` | Register a service under the given name |
| `get(name, default=None)` | `service \| default` | Retrieve a mounted service |
| `load(name)` | `service \| None` | Call `service.auto_load()` once, mark as loaded |
| `start_all()` | `dict` | Load every mounted service |
| `stop_all()` | `None` | Call `close()` / `shutdown()` on all services |
| `snapshot()` | `dict` | Return `{mode, mount_index, runtime_index, config_index}` |
| `collect_cli_commands()` | `dict[str, dict]` | Ask each service for its CLI sub-commands |
| `dispatch_plugin_cli(plugin_name, argv)` | `int` | Route `argv` to the named plugin's handler; returns exit code |

---

## `plugin_registry` — `services/plugin_registry.py`

Utility module for decoupled plugin mounting and config default synchronization.

| Function | Returns | Description |
|---|---|---|
| `normalize_plugin_name(name)` | `str` | Normalize aliases (`web-user` -> `web_user`, `deps` -> `dependency_manager`) |
| `list_builtin_plugins()` | `list[str]` | Built-in plugin keys |
| `ensure_plugin_defaults(config, plugin_name)` | `bool` | Inject missing defaults into `RESOURCES.service_plugins.<plugin>` |
| `sync_all_plugin_defaults(config)` | `bool` | Ensure defaults for all built-ins |
| `ensure_and_mount_plugin(node, plugin_name, load=False, mode='runtime')` | `service` | Ensure config defaults, mount service, optionally load |

---

## `TUIService` — `services/tui/main.py`

Section-aware terminal UI snapshot renderer with interactive live mode.

### Constructor

```python
TUIService(node: OpenSynaptic)
```

### Methods

| Method | Returns | Description |
|---|---|---|
| `render_section(name)` | `dict` | Single section snapshot (`identity`/`config`/`transport`/`pipeline`/`plugins`/`db`) |
| `render_sections(sections=None)` | `dict` | Multiple sections; `None` = all |
| `build_snapshot()` | `dict` | Full snapshot dict (all sections + timestamp) |
| `render_text(sections=None)` | `str` | JSON-formatted string of `render_sections()` |
| `run_once(sections=None)` | `str` | Alias for `render_text()` |
| `run_bios(interval=2.0, section=None)` | `None` | Interactive BIOS-style view with hotkeys |
| `run_interactive(interval=2.0, sections=None)` | `None` | Backward-compatible wrapper to BIOS mode |
| `get_cli_commands()` | `dict` | Returns `{"render": fn, "interactive": fn, "bios": fn}` |

---

## `TestPlugin` — `services/test_plugin/main.py`

ServiceManager-mountable test runner exposing component, stress, integration, and comparison suites.

### Constructor

```python
TestPlugin(node: OpenSynaptic | None = None)
```

### Methods

| Method | Returns | Description |
|---|---|---|
| `run_component(verbosity=1)` | `(ok, fail, result)` | Run all `unittest.TestCase` component tests |
| `run_stress(total=200, workers=8, sources=6, progress=True, core_backend=None, require_rust=False, header_probe_rate=0.0, batch_size=1, processes=1, threads_per_process=None, chain_mode='core')` | `(summary_dict, fail_count)` | Run concurrent pipeline stress test |
| `run_all(stress_total=200, stress_workers=8, stress_sources=6, verbosity=1, progress=True, core_backend=None, require_rust=False, header_probe_rate=0.0, batch_size=1, processes=1, threads_per_process=None, chain_mode='core')` | `dict` | Run component + stress and return combined report |
| `run_integration()` | `(ok, fail, result)` | Run integration test suite |
| `get_cli_commands()` | `dict` | Returns handlers including `component`, `stress`, `all`, `compare`, `full_load`, `integration`, `audit` |

---

## `WebUserService` — `services/web_user/main.py`

HTTP management-entry plugin with a browser dashboard and control APIs.

| Method | Returns | Description |
|---|---|---|
| `start(host=None, port=None)` | `bool` | Start web service thread (defaults from `RESOURCES.service_plugins.web_user`) |
| `stop()` | `bool` | Stop web service |
| `status()` | `dict` | Runtime state (`running`, `users`, `data_file`, `uptime_s`) |
| `build_dashboard()` | `dict` | Aggregated node snapshot for Web dashboard (`identity`, `plugins`, `transport`, `pipeline`, `users`) |
| `get_cli_commands()` | `dict` | Returns `start/stop/status/dashboard/list/add/update/delete` handlers |

HTTP routes:

- `GET /` - browser UI
- `GET /health`, `GET /api/health`
- `GET /api/dashboard`
- `GET /api/dashboard?sections=identity,transport`
- `GET /api/ui/config`
- `PUT /api/ui/config`
- `GET /api/options/schema?only_writable=1`
- `PUT /api/options`
- `GET /api/config?key=a.b.c`
- `PUT /api/config`
- `GET /api/plugins`, `POST /api/plugins`
- `GET /api/transport`, `POST /api/transport`
- `GET /users`
- `POST /users`
- `PUT /users/{username}`
- `DELETE /users/{username}`

Write endpoints are controlled by `web_user.read_only` and `web_user.writable_config_prefixes`.
When `web_user.auth_enabled=true`, management calls require `X-Admin-Token`.

---

## `DependencyManagerPlugin` — `services/dependency_manager/main.py`

Dependency inspection and repair plugin.

| Command | Description |
|---|---|
| `check` | Compare `pyproject.toml` dependencies with installed packages |
| `doctor` | Run `pip check` |
| `sync` | Install all declared dependencies |
| `repair` | Install only missing dependencies |
| `install` | Install one named dependency |

---

## Logging

Use the `os_log` singleton:

```python
from opensynaptic.utils import os_log

os_log.info('MODULE', 'EVENT', 'message', {'context': 'dict'})
os_log.err('MODULE', 'EVENT', exception, {'context': 'dict'})
os_log.log_with_const('info', LogMsg.READY, root='/path/to/root')
```

All message templates live in `utils/constants.py:MESSAGES`.  
Add a `LogMsg` enum member before using it with `log_with_const`.
