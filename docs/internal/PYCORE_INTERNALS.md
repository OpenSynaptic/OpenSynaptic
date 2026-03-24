# PyCore Internals Reference

Deep-dive API reference for every class, method, and data contract in
`src/opensynaptic/core/pycore/`.  
This document is the primary source used to define the Rust `rscore` API.

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [Data Contracts](#2-data-contracts)
3. [OpenSynapticStandardizer](#3-opensynapticstandardizer)
4. [OpenSynapticEngine](#4-opensynapticengine)
5. [OSVisualFusionEngine](#5-osvisualfusionengine)
6. [OSHandshakeManager / CMD](#6-oshandshakemanager--cmd)
7. [OpenSynaptic (Orchestrator)](#7-opensynaptic-orchestrator)
8. [TransporterManager](#8-transportermanager)
9. [Security Primitives](#9-security-primitives)
10. [Buffer Utilities](#10-buffer-utilities)
11. [Error Handling Conventions](#11-error-handling-conventions)
12. [Thread-Safety Contracts](#12-thread-safety-contracts)

---

## 1. Pipeline Overview

```
sensors: list[list]
    │
    ▼
OpenSynapticStandardizer.standardize()
    │   input:  [[sensor_id, status, float_value, unit_str], ...]
    │   output: SensorFact (dict)
    │
    ▼
OpenSynapticEngine.compress()
    │   input:  SensorFact
    │   output: compressed_str  (Base62 + URL-safe Base64 text)
    │
    ▼  raw_input_str = f"{assigned_id};{compressed_str}"
    │
    ▼
OSVisualFusionEngine.run_engine()
    │   input:  raw_input_str, strategy ∈ {"FULL","DIFF"}
    │   output: BinaryFrame (bytes)
    │
    ▼
transporter.send(binary_frame, config)
    │   medium ∈ {"UDP","TCP","UART","RS485","CAN","LoRa","MQTT",...}
    └─► wire
```

**Receive path (mirror):**

```
wire bytes
    │
    ▼
OSVisualFusionEngine.decompress()   or
OSHandshakeManager.classify_and_dispatch()
    │   output: decoded SensorFact dict  or  HandshakeResult
```

---

## 2. Data Contracts

### 2.1 SensorFact (input / output of standardiser)

All keys use `s{n}_` prefix for sensor slots (n starts at 1).

```python
{
    "id":    str,          # device identifier
    "s":     str,          # device status string  ("ONLINE", "OFFLINE", …)
    "t":     int,          # UNIX timestamp (seconds)

    # per-sensor fields (n = 1, 2, 3, …)
    "s1_id": str,          # sensor ID
    "s1_s":  str,          # sensor status string
    "s1_v":  float | int,  # normalised value (in SI base unit)
    "s1_u":  str,          # physical attribute string ("Pressure", "Temperature", …)
                           # compound: "Length/Time"  (numerator/denominator)

    # optional extras (from **kwargs passed to standardize())
    "geohash": str,        # geo location hash
    "url":     str,        # resource URL
    "msg":     str,        # supplementary message
}
```

### 2.2 CompressedString format

```
{device_id}.{state_symbol}.{ts_b64url}|{sensor_segments}{extra_segments}
```

- **ts_b64url** – 6-byte big-endian millisecond UNIX timestamp, URL-safe Base64, no padding
- **sensor_segment** – `{sensor_id}>{state_sym}.{unit_token}:{value_b62}|`
- **unit_token** – compressed unit (see §4.2); `Z` means unknown
- **extra_segments** – `&{geohash}|`, `#{url_b64}|`, `@{msg_b64}`

### 2.3 BinaryFrame layout

```
Offset  Size      Field
──────  ────      ─────────────────────────────────────────────────────
0       1 byte    CMD byte
1       1 byte    route_count  (N)
2       N×4       route IDs (big-endian uint32 each; last = source AID)
2+N×4   1 byte    template ID (TID, decimal zfill-2, stored as uint8)
3+N×4   6 bytes   timestamp (big-endian uint64 bytes [2..8], i.e. 6 LSB)
9+N×4   L bytes   body  (CMD-dependent; may be XOR-encrypted)
9+N×4+L 1 byte    CRC-8  (poly=0x07, init=0x00)  over body
10+N×4+L 2 bytes  CRC-16/CCITT (poly=0x1021, init=0xFFFF) over entire frame minus last 2 bytes
```

For a single-hop packet (N=1):

```
[CMD:1][1:1][AID:4][TID:1][TS:6][BODY:L][CRC8:1][CRC16:2]  total = 15+L bytes
```

### 2.4 CMD Byte Values

| Constant           | Value | Direction | Description                          |
|--------------------|-------|-----------|--------------------------------------|
| `DATA_FULL`        | 0x3F  | Node→Server | Full payload (template + data)     |
| `DATA_FULL_SEC`    | 0x40  | Node→Server | Full payload, XOR-encrypted         |
| `DATA_DIFF`        | 0xAA  | Node→Server | Differential update (changed slots) |
| `DATA_DIFF_SEC`    | 0xAB  | Node→Server | Differential, XOR-encrypted         |
| `DATA_HEART`       | 0x7F  | Node→Server | Heartbeat (no value change)         |
| `DATA_HEART_SEC`   | 0x80  | Node→Server | Heartbeat, XOR-encrypted            |
| `ID_REQUEST`       | 0x01  | Node→Server | Request a device ID                 |
| `ID_ASSIGN`        | 0x02  | Server→Node | Assign a device ID                  |
| `ID_POOL_REQ`      | 0x03  | Node→Server | Request a batch of IDs              |
| `ID_POOL_RES`      | 0x04  | Server→Node | Batch ID assignment                 |
| `HANDSHAKE_ACK`    | 0x05  | Both        | Positive acknowledgement            |
| `HANDSHAKE_NACK`   | 0x06  | Both        | Negative acknowledgement            |
| `PING`             | 0x09  | Both        | Liveness probe                      |
| `PONG`             | 0x0A  | Both        | Liveness reply                      |
| `TIME_REQUEST`     | 0x0B  | Node→Server | Request server timestamp            |
| `TIME_RESPONSE`    | 0x0C  | Server→Node | Server timestamp payload            |
| `SECURE_DICT_READY`| 0x0D  | Server→Node | Session key exchange confirmation   |
| `SECURE_CHANNEL_ACK`|0x0E  | Node→Server | Encrypted channel acknowledged      |

**CMD classification helpers** (on `CMD` class):

```python
CMD.DATA_CMDS        # {0x3F, 0x40, 0xAA, 0xAB, 0x7F, 0x80}
CMD.PLAIN_DATA_CMDS  # {0x3F, 0xAA, 0x7F}
CMD.SECURE_DATA_CMDS # {0x40, 0xAB, 0x80}
CMD.CTRL_CMDS        # all handshake/ID/time CMDs
CMD.BASE_DATA_CMD    # dict: secure→plain mapping
CMD.SECURE_DATA_CMD  # dict: plain→secure mapping
```

### 2.5 HandshakeResult

Return value of `classify_and_dispatch()` and all `_handle_*` methods:

```python
{
    "type":     str,   # "DATA" | "CTRL" | "UNKNOWN" | "ERROR"
    "cmd":      int,   # raw CMD byte
    "result":   dict,  # decoded payload or error dict
    "response": bytes | None,  # optional reply packet to send back
}
```

### 2.6 SecureSession (internal dict)

```python
{
    "last":               int,           # last-seen UNIX timestamp
    "peer_addr":          str | None,    # stringified (ip, port) tuple
    "first_plaintext_ts": int | None,    # timestamp of first plaintext packet
    "pending_timestamp":  int | None,    # candidate key derivation timestamp
    "pending_key":        bytes | None,  # 32-byte session key candidate
    "pending_key_hex":    str | None,
    "key":                bytes | None,  # confirmed 32-byte XOR session key
    "key_hex":            str | None,
    "dict_ready":         bool,          # key exchange complete
    "decrypt_confirmed":  bool,          # first successful decryption done
    "state": str,  # "INIT" | "PLAINTEXT_SENT" | "DICT_READY" | "SECURE"
}
```

---

## 3. OpenSynapticStandardizer

**File:** `standardization.py`  
**Responsibility:** Convert raw sensor readings into normalised (SI base-unit) `SensorFact` dicts.

### 3.1 Constructor

```python
OpenSynapticStandardizer(config_path: str = 'Config.json')
```

| Init step | Detail |
|---|---|
| Load `Config.json` | Reads `engine_settings`, `payload_switches`, `RESOURCES.root` |
| Locate `libraries/Units/` | Walks `RESOURCES.root` → `libraries/` → fallback to `BASE_DIR/OS_Library` |
| Load `Prefixes.json` | Builds `self.prefixes` dict and `self.sorted_prefixes` (sorted longest-first) |
| Load disk cache | Reads `cache/standardization_cache.json` → `self.registry` |

**Key instance attributes:**

| Attribute | Type | Description |
|---|---|---|
| `config` | `dict` | Loaded `Config.json` |
| `precision` | `int` | Decimal precision for normalised values |
| `switches` | `dict` | `payload_switches` section from config |
| `prefixes` | `dict[str, dict]` | SI prefix definitions (decimal + binary) |
| `sorted_prefixes` | `list[str]` | Prefix keys sorted by length (longest first) for greedy matching |
| `registry` | `dict` | In-memory cache of resolved unit laws |
| `lib_units_dir` | `str` | Absolute path to the `Units/` JSON library directory |

### 3.2 `standardize(device_id, device_status, sensors, **kwargs) → dict`

Main pipeline entry point.

**Algorithm:**

```
for each sensor in sensors:
    1. Parse [sensor_id, sensor_status, value, unit_raw]
    2. unit_raw may be str (single unit) or tuple/list (compound unit: numerator/denominator)
    3. For each unit string: call _resolve_unit_law(unit_str)
    4. Apply linear transform: normalised_value = raw_value * factor + offset
    5. Derive compound physical_attribute string ("Length2/Time" etc.)
    6. Append s{n}_id, s{n}_s, s{n}_v, s{n}_u to fact dict
```

**Error handling:** Any individual sensor exception is caught and logged; that sensor is skipped (`skip_on_error` semantics).

### 3.3 `_resolve_unit_law(unit_str) → dict | None`

Resolve a unit string to a law dict:

```python
{
    "physical_attribute":  str,    # e.g. "Pressure"
    "to_standard_factor":  float,  # multiply raw value by this
    "to_standard_offset":  float,  # then add this (for temperature °C → K)
}
```

**Resolution order:**

1. Check `self.registry` cache (fast path)
2. Strip inverse prefix `"1/"` → set `is_inv = True`
3. Strip trailing power digit (e.g. `"m2"` → `work="m"`, `pwr=2`)
4. `_deep_search_in_atoms(work)` — scan all `libraries/Units/*.json`
5. If not found: greedy-match SI prefix from `self.sorted_prefixes`, then look up base unit; apply prefix factor
6. Raise `pwr` and optionally invert factor
7. Cache result in `self.registry`; mark `_is_dirty = True`

**Special aliases** in `_deep_search_in_atoms`:

| Input | Resolved to |
|---|---|
| `"cel"` | `"Cel"` |
| `"hour"` | `"h"` |
| `"celsius"` | `"degree_celsius"` |

### 3.4 `_deep_search_in_atoms(unit_str) → dict | None`

Scans every `*.json` in `lib_units_dir` looking for a `units[unit_str]` entry.  
Tries exact match, then lowercase match, then `ucum_code` field match.  
Returns the unit definition dict or `None`.

### 3.5 `_save_cache()`

Writes `self.registry` to `cache/standardization_cache.json` only if `_is_dirty`.  
Format:

```json
{
    "cached_units": { "<unit_str>": { "physical_attribute": "...", "to_standard_factor": 1.0, "to_standard_offset": 0.0 } },
    "updated_at": 1700000000,
    "engine": "OS-Standardizer-v4-GCD-Final"
}
```

---

## 4. OpenSynapticEngine

**File:** `solidity.py`  
**Responsibility:** Base62 compress/decompress `SensorFact` dicts to/from a compact text wire format.

### 4.1 Constructor

```python
OpenSynapticEngine(config_path: str | None = None)
```

| Init step | Detail |
|---|---|
| Load config | `engine_settings.precision` (default 4), `engine_settings.use_ms` |
| Instantiate `Base62Codec(precision=precision)` | Native ctypes binding |
| Build `BIT_SWITCH` / `SCALE_MAP` | SI prefix scaling lookup tables |
| Locate symbol table | `RESOURCES.prefixes/symbols` → `data/symbols.json` → `libraries/OS_Symbols.json` |
| Load `solidity_cache.json` | Populates `self.registry` with persisted unit token cache |

**Key attributes:**

| Attribute | Type | Description |
|---|---|---|
| `codec` | `Base62Codec` | Native Base62 encode/decode (ctypes) |
| `precision_val` | `int` | `10 ** precision` — fixed-point scale factor |
| `BIT_SWITCH` | `dict` | Maps hex key → `{macro, micro, f}` for SI prefix auto-scaling |
| `SCALE_MAP` | `dict` | `{prefix_char: scale_factor}` for both macro and micro prefixes |
| `_units_map` | `dict` | `{ucum_name_lower: numeric_symbol}` from `OS_Symbols.json` |
| `_states_map` | `dict` | `{state_name_lower: state_code}` |
| `REV_UNIT` | `dict` | Reverse: `{symbol: ucum_name}` |
| `REV_STATE` | `dict` | Reverse: `{code: state_name}` |
| `_unit_token_cache` | `dict` | LRU-like cache for `_compress_unit()` results |
| `_b62_encode_cache` | `dict` | LRU-like cache (max 16384 entries) for `encode_b62()` |

### 4.2 `compress(fact: dict) → str`

Encodes a `SensorFact` to the compact text wire format.

**Timestamp encoding:**

```python
t_raw = int(t_ms)          # milliseconds since epoch
t_bin = struct.pack('>Q', t_raw)[2:]  # 6 LSB bytes of uint64
t_enc = base64.urlsafe_b64encode(t_bin).rstrip('=')
```

**Header:**

```
{device_id}.{state_symbol}.{t_enc}|
```

**Sensor segment** (repeated for each s1…sN):

```
{sensor_id}>{state_sym}.{unit_token}:{value_b62}|
```

where `unit_token = _compress_unit(s{n}_u)`.

**Optional extras** (appended after sensor segments):

```
&{geohash}|          if "geohash" in fact
#{url_b64}|          if "url" in fact   (strips "https://", then URL-safe B64)
@{msg_b64}           if "msg" in fact
```

### 4.3 `decompress(b62_str: str) → dict`

Reverses `compress()`.  
- Parses header → `id`, `s`, `t_raw`
- For each `>` segment → `s{n}_id`, `s{n}_s`, `s{n}_v`, `s{n}_u`
- Handles `&` (geohash), `#` (url), `@` (msg)
- Applies `REV_UNIT` / `REV_STATE` mappings on decode

### 4.4 `_compress_unit(unit_str) → str`

Converts a physical attribute string (e.g. `"1000Pressure"`) to a compact unit token.

**Algorithm:**

```
split by "/"  (numerator / denominator parts)
for each part:
    split_coeff_attr_power(part) → (coeff, attr, power)
    if coeff present:
        try to absorb into SI prefix (macro scale: da, k, M, G)
        encode coeff as B62 if non-trivial
        format: "{coeff_b62},{symbol_code}{power}"
    else:
        format: "{symbol_code}{power}"
join with "/"
```

Returns `"Z"` for unknown or empty units.  
Results are memoised in `_unit_token_cache`.

### 4.5 `encode_b62(n, use_precision=True) → str`

Wraps `Base62Codec.encode()` with a fixed-point LRU cache.

- `use_precision=True` → multiply by `precision_val` before encoding (for float sensor values)
- `use_precision=False` → encode raw integer (for coefficients and IDs)

### 4.6 `decode_b62(s, use_precision=True) → float`

Wraps `Base62Codec.decode()`.  
`use_precision=True` → divide result by `precision_val`.

### 4.7 `_split_coeff_attr_power(p) → (coeff, attr, power)`

Pure parser: splits a unit part like `"1000Pressure2"` into `("1000", "Pressure", "2")`.

### 4.8 `_strip_sym_and_power(sym_p) → (base, power)`

Splits `"kg2"` → `("kg", "2")`. Used in `decompress()`.

---

## 5. OSVisualFusionEngine

**File:** `unified_parser.py`  
**Responsibility:** Encode `SensorFact` text into a binary frame, apply template learning and DIFF compression, and decode frames back to dicts.

### 5.1 Constructor

```python
OSVisualFusionEngine(config_path: str | None = None)
```

| Init step | Detail |
|---|---|
| Set `self.base_dir` | From `config_path` parent or `ctx.root` |
| Resolve registry dir | `ctx.registry_dir` → `data/device_registry/` |
| `_set_local_id(0)` | Pre-initialize local AID to 0 |
| Decode `assigned_id` from config | Accepts `int`, digit string, or Base62 string |

**Key attributes:**

| Attribute | Type | Description |
|---|---|---|
| `local_id` | `int` | This node's numeric device ID |
| `local_id_str` | `str` | String form of `local_id` |
| `_single_route_ids` | `tuple[int]` | `(local_id,)` — pre-built single-hop route tuple |
| `_single_route_bin` | `bytes` | `struct.pack('>I', local_id)` — pre-built 4-byte AID |
| `_RAM_CACHE` | `dict` | `{aid_str: RegistryEntry}` — in-memory device registry cache |
| `_cache_lock` | `RLock` | Protects `_RAM_CACHE` |
| `root_dir` | `str` | Device registry base directory |
| `protocol` | `OSHandshakeManager` | Injected after construction by `OpenSynaptic` |

### 5.2 `run_engine(raw_input, strategy='DIFF') → bytes`

Core encode entry point.

**Input format:** `"{aid};{compressed_b62_str}"` or raw bytes/bytearray/memoryview.

**Algorithm:**

```
1. _auto_decompose(raw_input)
   → (ts_str, sig, vals_bin, src_aid, route_ids)

2. _get_active_registry(src_aid)   ← per-device template store

3. strategy == 'FULL':
   if vals_bin == cached_vals:
       cmd = DATA_HEART (0x7F)     # no change, heartbeat
   else:
       cmd = DATA_FULL (0x3F)      # store template + send full body
       update cached_vals

4. strategy == 'DIFF':
   if no existing template or len mismatch:
       cmd = DATA_FULL (0x3F)
   elif vals_bin == cached_vals:
       cmd = DATA_HEART (0x7F)
   else:
       compute bitmask of changed slots
       encode changed vals: {mask_bytes}{[len,val]...}
       cmd = DATA_DIFF (0xAA)

5. If security enabled for src_aid:
   cmd = secure_variant_cmd(cmd)   # 0x3F→0x40, 0xAA→0xAB, 0x7F→0x80

6. _finalize_bin(cmd, tid, ts_str, body, route_ids, src_aid)
```

### 5.3 `_finalize_bin(cmd, tid, ts_str, body_bytes, route_ids, src_aid) → bytes`

Assembles the binary frame:

```python
frame = bytearray(2 + N*4 + 1 + 6 + len(body) + 1 + 2)
frame[0]     = wire_cmd
frame[1]     = route_count
frame[2:2+N*4]  = route_id_bytes   # big-endian uint32 each
frame[2+N*4]    = int(tid)
frame[3+N*4:9+N*4]  = ts_raw[0:6]  # 6 LSB bytes of 8-byte timestamp
frame[9+N*4:9+N*4+L] = body_or_xor_body
frame[9+N*4+L]  = crc8(body)
frame[-2:]      = crc16_ccitt(frame[:-2])  # big-endian uint16
```

- CRC-8: poly=0x07, init=0x00, computed over plaintext body
- CRC-16/CCITT: poly=0x1021, init=0xFFFF, computed over entire frame minus last 2 bytes
- If security enabled: `xor_payload_into(body, session_key, crc8_val & 0x1F, out_slice)`

### 5.4 `decompress(packet: bytes) → dict`

Decode a binary frame.

**Algorithm:**

```
1. Parse header: cmd, route_count (r_cnt), source_aid
2. Verify CRC-16 (entire frame minus last 2 bytes)
3. Extract TID, timestamp (6 bytes → uint64)
4. If secure cmd: XOR-decrypt body using session key
5. Verify CRC-8 over plaintext body
6. Dispatch on base_cmd:
   DATA_FULL (0x3F):
       decode UTF-8 body → compressed string
       _decompose_for_receive() → learn template + extract vals
       call OpenSynapticEngine().decompress(raw_str)
   DATA_HEART (0x7F):
       reconstruct payload from cached template + cached vals
       call OpenSynapticEngine().decompress(reconstructed)
   DATA_DIFF (0xAA):
       read bitmask, patch only changed slots in cached vals
       reconstruct payload, call decompress()
7. Attach __packet_meta__ to result dict
```

**`__packet_meta__` fields:**

```python
{
    "cmd":            int,   # raw CMD byte
    "base_cmd":       int,   # plain CMD (secure variant mapped back)
    "secure":         bool,
    "source_aid":     int,
    "crc16_ok":       bool,
    "crc8_ok":        bool,
    "timestamp_raw":  int,   # decoded ms timestamp
    "tid":            str,   # zero-padded template ID string
    "template_learned": bool,  # True when a new template was registered (FULL only)
}
```

### 5.5 `_auto_decompose(raw_input) → tuple | None`

Parse `"{aid};{header}|{sensor_segs}|"` into a 5-tuple:

```python
(ts_str, sig_template, vals_bin, src_aid, route_ids)
```

- `sig_template` — template string with `\x01` placeholders for variable fields
- `vals_bin` — list of `bytes` for each variable field
- `src_aid` — `int(self.local_id)` (outbound path always uses local AID)
- `route_ids` — `self._single_route_ids`

Accepts `bytes`, `bytearray`, `memoryview`, or `str` input.

### 5.6 `_decompose_for_receive(raw_input) → (sig, vals_bin) | None`

Server-side twin of `_auto_decompose`. Strips the `{aid};` prefix then builds:

- `sig` — template signature string with `\x01` placeholders
- `vals_bin` — list of `bytes` (metadata + value for each sensor)

### 5.7 `_get_active_registry(aid_str) → RegistryEntry`

Lazy-loads the per-device template registry from disk to RAM cache.

**RegistryEntry structure:**

```python
{
    "data":         dict,          # persisted JSON: {"aid": str, "templates": {tid: {sig, last_vals_bin}}}
    "path":         str,           # absolute path to registry JSON file
    "dirty":        bool,          # write-back flag
    "lock":         RLock,         # per-device write lock
    "runtime_vals": dict,          # {tid: [bytes, ...]} decoded last values
    "sig_index":    dict,          # {sig_str: tid} reverse index
}
```

Registry files are sharded by device ID:

```
data/device_registry/{id[0:2]}/{id[2:4]}/{decimal_id}.json
```

### 5.8 `_sync_to_disk(aid_str)`

Writes the `RegistryEntry` back to disk if `dirty=True`. Thread-safe via per-device lock.  
Encodes `runtime_vals` as Base64 before persisting.

### 5.9 `_set_local_id(local_id: int)`

Atomically update `local_id`, `local_id_str`, `_single_route_ids`, `_single_route_bin`.

### 5.10 `_decode_ts_token(ts_str) → int`

URL-safe Base64 decode a 6-byte timestamp back to a uint64 integer (milliseconds).

### 5.11 `_resolve_outbound_security(src_aid) → (bool, bytes | None)`

Asks `self.protocol.should_encrypt_outbound(src_aid)` and retrieves the session key.  
Returns `(False, None)` if no protocol is attached.

### 5.12 `relay(packet) → bytes`

Re-encode a packet through the engine (pass-through relay).

---

## 6. OSHandshakeManager / CMD

**File:** `handshake.py`  
**Responsibility:** Binary packet framing for control messages, device-ID negotiation, time sync, and encrypted session management.

### 6.1 CMD Class (constants)

See §2.4 for the full table.

### 6.2 OSHandshakeManager Constructor

```python
OSHandshakeManager(
    target_sync_count: int = 3,
    registry_dir: str | None = None,
    expire_seconds: int = 86400,
)
```

| Attribute | Type | Description |
|---|---|---|
| `target_sync_count` | `int` | Min successful transmissions before switching to DIFF strategy |
| `registry_status` | `dict` | `{aid_str: {count, last, state}}` |
| `secure_sessions` | `dict` | `{aid_str: SecureSession}` |
| `_lock` | `Lock` | Thread safety for `registry_status`, `secure_sessions` |
| `_seq_counter` | `int` | Rolling uint16 sequence counter for packets |
| `id_allocator` | `IDAllocator \| None` | Injected by `OpenSynaptic.__init__` |
| `parser` | `OSVisualFusionEngine \| None` | Injected by `OpenSynaptic.__init__` |
| `min_valid_timestamp` | `int` | Minimum acceptable UNIX timestamp (default 1,000,000) |
| `last_server_time` | `int` | Most recent server timestamp from `TIME_RESPONSE` |

### 6.3 `classify_and_dispatch(packet: bytes, addr=None) → HandshakeResult`

Main inbound packet router.

```
if cmd in DATA_CMDS:
    call parser.decompress(packet)
    check CRC-16; if fail → return without side-effects
    if plaintext data and no session → establish_remote_plaintext() + send SECURE_DICT_READY response
    if secure data and not yet confirmed → mark_secure_channel() + send SECURE_CHANNEL_ACK

if cmd in CTRL_CMDS:
    route to _handle_ctrl(cmd, packet, addr)
```

### 6.4 Strategy Management

#### `get_strategy(aid, has_template) → "FULL_PACKET" | "DIFF_PACKET"`

```
if no registry entry:
    if persistence found or has_template → set count=target_sync_count (SYNCED)
    else → count=0 (HANDSHAKING)

if has_template and session.dict_ready → DIFF_PACKET (encrypted path)
if not has_template or count < target_sync_count → FULL_PACKET
else → DIFF_PACKET
```

Also calls `_cleanup_expired()` to evict stale entries.

#### `commit_success(aid)`

Increments `registry_status[aid].count`.  
Transitions `state` to `'SYNCED'` once `count >= target_sync_count`.

### 6.5 Session Security Methods

| Method | Signature | Description |
|---|---|---|
| `note_local_plaintext_sent` | `(aid, ts_raw, addr) → session` | Derive `pending_key = derive_session_key(aid, ts_raw)` and store |
| `establish_remote_plaintext` | `(aid, ts_raw, addr) → session` | Derive key and mark `dict_ready=True` (server side) |
| `confirm_secure_dict` | `(aid, ts_raw, addr) → bool` | Promote pending key to active key |
| `mark_secure_channel` | `(aid, addr) → session` | Set `decrypt_confirmed=True`, state→`"SECURE"` |
| `has_secure_dict` | `(aid) → bool` | True if session has `dict_ready` flag |
| `should_encrypt_outbound` | `(aid) → bool` | True if session has both `dict_ready` and `key` |
| `get_session_key` | `(aid) → bytes \| None` | Return 32-byte session key |

### 6.6 Packet Builders

| Method | Output | Bytes layout |
|---|---|---|
| `build_id_request(meta)` | `bytes` | `[0x01][seq:2][json_meta]` |
| `build_id_pool_request(count, meta)` | `bytes` | `[0x03][seq:2][count:2][json_meta]` |
| `build_ping()` | `bytes` | `[0x09][seq:2]` |
| `build_time_request()` | `bytes` | `[0x0B][seq:2]` |
| `_build_id_assign(seq, aid)` | `bytes` | `[0x02][seq:2][aid:4]` |
| `_build_id_pool_response(seq, pool)` | `bytes` | `[0x04][seq:2][count:2][id:4]*N` |
| `_build_ack(seq)` | `bytes` | `[0x05][seq:2]` |
| `_build_nack(seq, reason)` | `bytes` | `[0x06][seq:2][reason_utf8]` |
| `_build_pong(seq)` | `bytes` | `[0x0A][seq:2]` |
| `_build_time_response(seq, ts)` | `bytes` | `[0x0C][seq:2][ts:8]` |
| `_build_secure_dict_ready(aid, ts)` | `bytes` | `[0x0D][aid:4][ts:8]` |
| `_build_secure_channel_ack(aid)` | `bytes` | `[0x0E][aid:4]` |

### 6.7 Transport-Level Handshake Helpers

These are convenience loops wrapping the packet builders + `classify_and_dispatch`:

```python
request_id_via_transport(send_fn, recv_fn, device_meta, timeout) → int | None
request_id_pool_via_transport(send_fn, recv_fn, count, meta, timeout) → list[int]
request_time_via_transport(send_fn, recv_fn, timeout) → int | None
```

All three loop `classify_and_dispatch(resp)` until the expected reply CMD is seen or timeout expires.

---

## 7. OpenSynaptic (Orchestrator)

**File:** `core.py`  
**Responsibility:** Wire all subsystems together; provide the primary user-facing API.

### 7.1 Construction and Wiring Order

```
1. Load Config.json (via OSContext or explicit path)
2. OpenSynapticStandardizer(config_path)
3. OpenSynapticEngine(config_path)
4. OSVisualFusionEngine(config_path)
5. _sync_assigned_id_to_fusion()
6. IDAllocator(base_dir, start_id, end_id)
7. OSHandshakeManager(target_sync_count, registry_dir, expire_seconds)
8. protocol.id_allocator = id_allocator
9. protocol.parser      = fusion
10. fusion.protocol     = protocol
11. ServiceManager(config, mode='runtime')
12. sync_all_plugin_defaults(config)  → _save_config() if dirty
13. TransporterManager(self) → auto_load()
14. DatabaseManager.from_opensynaptic_config(config)  (optional)
15. db_manager mounted to service_manager
```

### 7.2 `transmit(sensors, device_id, device_status, **kwargs) → (bytes, int, str)`

Full pipeline call:

```python
# Pre-flight checks
if _is_id_missing(): raise RuntimeError

# Auto time-sync if timestamp looks invalid
if t < min_valid_timestamp and not protocol.has_secure_dict(aid):
    server_time = ensure_time()

# Stage 1: Standardize
fact = standardizer.standardize(device_id, device_status, sensors, **kwargs)

# Stage 1b: Optional DB export
if db_manager: db_manager.export_fact(fact)

# Stage 2: Compress
compressed_str = engine.compress(fact)
raw_input_str = f"{assigned_id};{compressed_str}"

# Stage 3: Strategy selection
decomp = fusion._auto_decompose(raw_input_str)
reg = fusion._get_active_registry(src_aid)
has_template = len(reg['data']['templates']) > 0
strategy_label = protocol.get_strategy(src_aid, has_template)
engine_strat = 'FULL' if strategy_label == 'FULL_PACKET' else 'DIFF'

# Stage 4: Fuse to binary
binary_packet = fusion.run_engine(raw_input_str, strategy=engine_strat)

# Post-flight
protocol.commit_success(src_aid)
if plaintext full packet: protocol.note_local_plaintext_sent(src_aid, ts_raw)
if reg.dirty: fusion._sync_to_disk(src_aid)

return (binary_packet, src_aid, strategy_label)
```

### 7.3 `dispatch(packet, medium) → bool`

```python
# Zero-copy path (default)
wire_packet = as_readonly_view(packet)   if zero_copy_enabled(config)
            # else:
wire_packet = ensure_bytes(packet)

driver = transporter_manager.get_driver(medium)
        or active_transporters[medium.lower()]

driver.send(wire_packet, self.config)
```

### 7.4 `ensure_id(server_ip, server_port, device_meta, timeout) → bool`

Skips if already assigned.  
Creates a `socket.SOCK_DGRAM` socket, delegates to `protocol.request_id_via_transport()`.  
Persists `assigned_id` to `Config.json` on success.

### 7.5 `ensure_time(server_ip, server_port, timeout) → int | None`

Creates a `socket.SOCK_DGRAM` socket, delegates to `protocol.request_time_via_transport()`.  
Calls `protocol.note_server_time(ts)` on success.

### 7.6 `dispatch_with_reply(packet, server_ip, server_port, timeout) → bytes | None`

UDP send + receive in one call.  
Routes the response through `protocol.classify_and_dispatch()`.

### 7.7 `receive(raw_bytes) → dict`

Thin wrapper: `fusion.decompress(raw_bytes)`.

### 7.8 `receive_via_protocol(raw_bytes, addr) → HandshakeResult`

Thin wrapper: `protocol.classify_and_dispatch(raw_bytes, addr)`.

---

## 8. TransporterManager

**File:** `transporter_manager.py`  
**Responsibility:** Unified registry across three transport tiers.

### 8.1 Protocol Sets

```python
APP_PROTOCOLS      = {'mqtt'}
TRANSPORT_PROTOCOLS = {'udp', 'tcp', 'quic', 'iwip', 'uip'}
PHYSICAL_PROTOCOLS  = {'uart', 'rs485', 'can', 'lora'}
```

### 8.2 `_migrate_resource_maps()`

Ensures `RESOURCES.application_status`, `transport_status`, `physical_status` all exist and mirrors them into the legacy `transporters_status` merged map.  
Auto-saves config if any key was added.

### 8.3 `auto_load() → dict`

```
TransporterService.auto_load()          → app-layer MQTT etc.
TransportLayerManager.discover()        → UDP, TCP, QUIC, lwIP, uIP
PhysicalLayerManager.discover()         → UART, RS-485, CAN, LoRa
```

### 8.4 `get_driver(medium) → driver | None`

Checks (in order): app-layer active transporters, transport-layer adapters, physical-layer adapters.  
Returns a driver object with a `send(payload, config) → bool` method.

---

## 9. Security Primitives

**File:** `utils/security/security_core.py`  
**Backing:** `utils/security/security_native.c` → `os_security.dll/.so`

### 9.1 `crc8(data, poly=0x07, init=0x00) → int`

CRC-8 over `data` (bytes-like). Returns 0–255.

### 9.2 `crc16_ccitt(data, poly=0x1021, init=0xFFFF) → int`

CRC-16/CCITT over `data` (bytes-like). Returns 0–65535.

### 9.3 `derive_session_key(assigned_id: int, timestamp_raw: int) → bytes`

Derives a 32-byte session key using BLAKE2b/SHA-256 mix keyed on `(aid, ts)`.  
Returns 32 opaque bytes.

### 9.4 `xor_payload(payload, key, offset) → bytes`

Rolling XOR cipher. `offset` is a byte offset into the key (for CRC-based nonce mixing).  
Returns new `bytes`.

### 9.5 `xor_payload_into(payload, key, offset, out_buffer) → int`

Zero-copy variant: writes XOR result directly into `out_buffer` (memoryview-compatible).  
Returns number of bytes written.

---

## 10. Buffer Utilities

**File:** `utils/buffer.py`

| Function | Signature | Description |
|---|---|---|
| `as_readonly_view` | `(Any) → memoryview` | Zero-copy view; UTF-8 encodes strings |
| `ensure_bytes` | `(Any) → bytes` | Materializes to bytes (socket boundary) |
| `payload_len` | `(Any) → int` | Length without materializing |
| `zero_copy_enabled` | `(config: dict) → bool` | Reads `engine_settings.zero_copy_transport` (default `True`) |
| `to_wire_payload` | `(payload: Any, config: Any, force_zero_copy: bool=False) → memoryview \| bytes` | Single-point helper used by pycore/service transport send paths |

---

## 11. Error Handling Conventions

All errors are routed through `os_log.err(MODULE, EVENT, exception, context_dict)`.

- `standardize()` catches per-sensor exceptions and continues.
- `decompress()` returns `{'error': str, '__packet_meta__': meta}` instead of raising.
- `run_engine()` returns `raw_input.encode()` as fallback if decomposition fails.
- `_get_active_registry()` returns an empty template set if the file is missing.
- Protocol classify_and_dispatch never raises; unknown CMDs return an `UNKNOWN` result.

---

## 12. Thread-Safety Contracts

| Component | Mechanism | Scope |
|---|---|---|
| `OSVisualFusionEngine._RAM_CACHE` | `RLock (_cache_lock)` | All cache reads/writes |
| Per-device RegistryEntry | `RLock (entry['lock'])` | Template mutation and disk sync |
| `OSHandshakeManager.registry_status` | `Lock (_lock)` | Strategy reads and commit_success |
| `OSHandshakeManager.secure_sessions` | Same `_lock` | Session creation/mutation |
| `IDAllocator` | Internal `Lock` | ID allocation and release |
| `OpenSynapticStandardizer.registry` | `_is_dirty` flag + single-writer assumption | Disk-writeback cache |
| `OpenSynapticEngine` caches | `_b62_encode_cache`, `_unit_token_cache` | Not locked; cleared-on-overflow strategy acceptable for caches |


