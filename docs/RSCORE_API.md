# RSCore API Design — OpenSynaptic Rust Core

**Purpose:** Define the complete Rust API for `rscore/` — a native Rust reimplementation of `pycore/`.  
**Source of truth:** `docs/PYCORE_INTERNALS.md`  
**Target crate path:** `src/opensynaptic/core/rscore/`  
**Language:** Rust (edition 2021)  
**FFI surface:** Python-callable via `pyo3`; also usable as a standalone `no_std`-compatible library.

---

## Table of Contents

1. [Crate Layout](#1-crate-layout)
2. [Cargo.toml Dependencies](#2-cargotoml-dependencies)
3. [Data Types (Shared)](#3-data-types-shared)
4. [Module: `security`](#4-module-security)
5. [Module: `codec` (Base62)](#5-module-codec-base62)
6. [Module: `standardizer`](#6-module-standardizer)
7. [Module: `engine` (Solidity)](#7-module-engine-solidity)
8. [Module: `fusion`](#8-module-fusion)
9. [Module: `handshake`](#9-module-handshake)
10. [Module: `transport`](#10-module-transport)
11. [Module: `node` (Orchestrator)](#11-module-node-orchestrator)
12. [PyO3 Bindings Layer](#12-pyo3-bindings-layer)
13. [Config Mapping](#13-config-mapping)
14. [Error Types](#14-error-types)
15. [Thread-Safety Model](#15-thread-safety-model)
16. [Implementation Notes & Divergences from PyCore](#16-implementation-notes--divergences-from-pycore)

---

## 1. Crate Layout

```
src/opensynaptic/core/rscore/
├── Cargo.toml
├── build.rs                  # optional: compile C security/codec shims
├── src/
│   ├── lib.rs                # crate root; re-exports + PyO3 module init
│   ├── error.rs              # OsError enum
│   ├── config.rs             # OsConfig, EngineSettings, SecuritySettings, Resources
│   ├── security.rs           # crc8, crc16, derive_session_key, xor_payload
│   ├── codec.rs              # Base62Codec, b62_encode, b62_decode
│   ├── standardizer.rs       # UnitRegistry, Standardizer, SensorFact
│   ├── engine.rs             # SolidityEngine, compress, decompress
│   ├── fusion.rs             # FusionEngine, run_engine, decompress
│   ├── handshake.rs          # Cmd, HandshakeManager, SecureSession
│   ├── transport.rs          # Transporter trait, TransportKind
│   ├── node.rs               # OpenSynapticNode (orchestrator)
│   └── py_bindings.rs        # #[pymodule] rscore + #[pyclass] wrappers
```

---

## 2. Cargo.toml Dependencies

```toml
[package]
name        = "opensynaptic-rscore"
version     = "0.1.0"
edition     = "2021"

[lib]
name        = "rscore"
crate-type  = ["cdylib", "rlib"]

[dependencies]
# Serialization
serde       = { version = "1", features = ["derive"] }
serde_json  = "1"

# Zero-copy byte buffers
bytes       = "1"

# Base64 (URL-safe, no padding)
base64      = "0.22"

# Parallel / concurrent primitives
parking_lot = "0.12"       # RwLock / Mutex with no poisoning

# Hashing for derive_session_key
blake2      = "0.10"
sha2        = "0.10"

# CRC
crc         = "3"

# Filesystem helpers
walkdir     = "2"

# PyO3 bridge (optional feature)
pyo3        = { version = "0.21", features = ["extension-module"], optional = true }

[features]
default    = ["python"]
python     = ["pyo3"]
no_std_compat = []     # strips serde_json / walkdir for embedded targets

[profile.release]
opt-level = 3
lto       = true
```

---

## 3. Data Types (Shared)

### 3.1 `SensorFact`

```rust
/// Normalised sensor fact produced by Standardizer and consumed by SolidityEngine.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SensorFact {
    /// Device identifier string
    pub id: String,
    /// Device status (e.g. "ONLINE")
    pub s: String,
    /// UNIX timestamp (seconds)
    pub t: u64,
    /// Variable-length sensor slots
    pub sensors: Vec<SensorSlot>,
    /// Optional geo-hash
    pub geohash: Option<String>,
    /// Optional resource URL (full, with https://)
    pub url: Option<String>,
    /// Optional supplementary message
    pub msg: Option<String>,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SensorSlot {
    pub id: String,
    /// Sensor status string
    pub status: String,
    /// Normalised SI value
    pub value: f64,
    /// Physical attribute string, e.g. "Pressure", "Length/Time"
    pub unit: String,
}
```

### 3.2 `BinaryFrame`

```rust
/// Encoded wire packet produced by FusionEngine.
pub struct BinaryFrame(pub bytes::Bytes);

impl BinaryFrame {
    pub fn as_bytes(&self) -> &[u8] { &self.0 }
    pub fn len(&self) -> usize { self.0.len() }
    pub fn is_empty(&self) -> bool { self.0.is_empty() }
}
```

### 3.3 `TransmitResult`

```rust
pub struct TransmitResult {
    pub frame:    BinaryFrame,
    pub aid:      u32,
    pub strategy: TransmitStrategy,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TransmitStrategy {
    FullPacket,
    DiffPacket,
}
```

### 3.4 `HandshakeResult`

```rust
#[derive(Debug, Clone)]
pub struct HandshakeResult {
    pub kind:     HandshakeKind,
    pub cmd:      u8,
    pub result:   serde_json::Value,
    pub response: Option<bytes::Bytes>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HandshakeKind {
    Data,
    Control,
    Unknown,
    Error,
}
```

### 3.5 `PacketMeta`

```rust
#[derive(Debug, Clone, Default)]
pub struct PacketMeta {
    pub cmd:              u8,
    pub base_cmd:         u8,
    pub secure:           bool,
    pub source_aid:       u32,
    pub crc16_ok:         bool,
    pub crc8_ok:          bool,
    pub timestamp_raw:    u64,    // milliseconds
    pub tid:              String,
    pub template_learned: bool,
}
```

---

## 4. Module: `security`

**File:** `src/security.rs`  
**Maps from:** `utils/security/security_core.py` + `security_native.c`

```rust
use bytes::Bytes;

/// CRC-8 (poly = 0x07, init = 0x00)
pub fn crc8(data: &[u8]) -> u8;
pub fn crc8_with(data: &[u8], poly: u8, init: u8) -> u8;

/// CRC-16/CCITT (poly = 0x1021, init = 0xFFFF)
pub fn crc16_ccitt(data: &[u8]) -> u16;
pub fn crc16_ccitt_with(data: &[u8], poly: u16, init: u16) -> u16;

/// Derive a 32-byte session key from (device_id, timestamp_raw).
/// Python: derive_session_key(assigned_id, timestamp_raw)
/// Implemented as: BLAKE2b-256( aid.to_le_bytes() ++ ts.to_le_bytes() )
pub fn derive_session_key(aid: u64, timestamp_raw: u64) -> [u8; 32];

/// XOR-stream cipher with key-offset nonce.
/// offset = crc8_val & 0x1F  (matches Python: crc8_val & 31)
pub fn xor_payload(payload: &[u8], key: &[u8], offset: u32) -> Bytes;

/// Zero-copy variant: write XOR result into out_buf.
/// Returns number of bytes written.
/// Precondition: out_buf.len() >= payload.len()
pub fn xor_payload_into(payload: &[u8], key: &[u8], offset: u32, out_buf: &mut [u8]) -> usize;
```

**Internal algorithm for `derive_session_key`:**

```rust
use blake2::{Blake2b, Digest};
// Must produce exactly 32 bytes matching the C implementation.
let mut h = Blake2b256::new();
h.update(&aid.to_le_bytes());
h.update(&timestamp_raw.to_le_bytes());
h.finalize().into()
```

> ⚠️ The exact algorithm must match `security_native.c:os_derive_session_key` byte-for-byte.
> Verify with the cross-platform test vector: `derive_session_key(42, 1700000000)` must equal the Python output.

---

## 5. Module: `codec` (Base62)

**File:** `src/codec.rs`  
**Maps from:** `utils/base62/base62.py` + `base62_native.c`

```rust
pub const CHARS: &[u8; 62] =
    b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";

/// Base62 codec with fixed-point precision.
pub struct Base62Codec {
    precision: u8,
    precision_val: i64,   // 10^precision
}

impl Base62Codec {
    pub fn new(precision: u8) -> Self;

    /// Encode a float with fixed-point scaling: round(n * 10^precision) → Base62.
    pub fn encode(&self, n: f64) -> String;

    /// Encode a raw integer without scaling.
    pub fn encode_raw(&self, n: i64) -> String;

    /// Decode a Base62 string and divide by 10^precision.
    pub fn decode(&self, s: &str) -> Result<f64, OsError>;

    /// Decode without dividing (raw integer).
    pub fn decode_raw(&self, s: &str) -> Result<i64, OsError>;
}

// Module-level helpers (use default precision=4 codec)
pub fn b62_encode(n: f64, precision: u8) -> String;
pub fn b62_decode(s: &str, precision: u8) -> Result<f64, OsError>;
pub fn b62_encode_raw(n: i64) -> String;
pub fn b62_decode_raw(s: &str) -> Result<i64, OsError>;
```

**Encoding algorithm:**

```rust
fn encode_inner(mut n: i64) -> String {
    if n == 0 { return "0".to_string(); }
    let negative = n < 0;
    if negative { n = -n; }
    let mut buf = Vec::new();
    while n > 0 {
        buf.push(CHARS[(n % 62) as usize]);
        n /= 62;
    }
    if negative { buf.push(b'-'); }
    buf.reverse();
    String::from_utf8(buf).unwrap()
}
```

---

## 6. Module: `standardizer`

**File:** `src/standardizer.rs`  
**Maps from:** `pycore/standardization.py`

### 6.1 UnitLaw

```rust
#[derive(Debug, Clone, serde::Deserialize)]
pub struct UnitLaw {
    pub physical_attribute:   String,
    pub to_standard_factor:   f64,
    pub to_standard_offset:   f64,
    pub can_take_prefix:      bool,
}
```

### 6.2 Standardizer

```rust
pub struct Standardizer {
    precision: u8,
    payload_switches: PayloadSwitches,
    prefixes: HashMap<String, PrefixDef>,
    sorted_prefix_keys: Vec<String>,      // sorted longest-first
    unit_cache: parking_lot::RwLock<HashMap<String, UnitLaw>>,
    lib_units_dir: PathBuf,
    cache_path: PathBuf,
    is_dirty: AtomicBool,
}

impl Standardizer {
    /// Load config and unit library from disk.
    pub fn new(config: &OsConfig, base_dir: &Path) -> Result<Self, OsError>;

    /// Load persisted unit cache from disk.
    pub fn load_cache(&mut self) -> Result<(), OsError>;

    /// Persist unit cache to disk if dirty.
    pub fn save_cache(&self) -> Result<(), OsError>;

    /// Main pipeline entry: normalise raw sensor readings.
    ///
    /// sensors: Vec<(sensor_id, status, raw_value, unit_str)>
    pub fn standardize(
        &self,
        device_id:     &str,
        device_status: &str,
        sensors:       &[(String, String, f64, String)],
        timestamp:     Option<u64>,
        extras:        Option<SensorExtras>,
    ) -> SensorFact;

    /// Resolve a unit string to its UnitLaw.
    /// Checks cache → library scan → prefix stripping.
    pub fn resolve_unit_law(&self, unit_str: &str) -> Option<UnitLaw>;

    /// Persist any newly resolved units to cache (debounced).
    pub fn flush_if_dirty(&self) -> Result<(), OsError>;
}

/// Optional extras for a sensor fact
#[derive(Debug, Default, Clone)]
pub struct SensorExtras {
    pub geohash: Option<String>,
    pub url:     Option<String>,
    pub msg:     Option<String>,
}
```

### 6.3 PayloadSwitches

```rust
#[derive(Debug, Clone, serde::Deserialize, Default)]
#[serde(rename_all = "PascalCase")]
pub struct PayloadSwitches {
    pub device_id:              bool,
    pub device_status:          bool,
    pub timestamp:              bool,
    pub sub_template_id:        bool,
    pub sensor_id:              bool,
    pub sensor_status:          bool,
    pub physical_attribute:     bool,
    pub normalized_value:       bool,
    pub geohash_id:             bool,
    pub supplementary_message:  bool,
    pub resource_url:           bool,
}
```

### 6.4 Unit Library Format (JSON)

```json
{
  "units": {
    "pascal": { "physical_attribute": "Pressure", "to_standard_factor": 1.0, "to_standard_offset": 0.0, "can_take_prefix": true, "ucum_code": "Pa" }
  }
}
```

---

## 7. Module: `engine` (Solidity)

**File:** `src/engine.rs`  
**Maps from:** `pycore/solidity.py`

```rust
pub struct SolidityEngine {
    codec:           Base62Codec,
    use_ms:          bool,
    units_map:       HashMap<String, String>,   // lowercase ucum → symbol code
    states_map:      HashMap<String, String>,   // lowercase state → code
    rev_unit:        HashMap<String, String>,   // symbol code → ucum name
    rev_state:       HashMap<String, String>,   // code → state name
    bit_switch:      Vec<BitSwitchEntry>,       // SI prefix scale entries
    scale_map:       HashMap<String, f64>,      // prefix char → factor
    unit_token_cache: parking_lot::Mutex<LruCache<String, String>>,
    b62_encode_cache: parking_lot::Mutex<LruCache<(u8, i64), String>>,
}

#[derive(Clone)]
struct BitSwitchEntry {
    pub macro_prefix: String,   // "k", "M", "G", "da"
    pub micro_prefix: String,   // "m", "u", "p", "d"
    pub factor:       f64,
}

impl SolidityEngine {
    pub fn new(config: &OsConfig, base_dir: &Path) -> Result<Self, OsError>;

    /// Compress a SensorFact to the wire text format.
    pub fn compress(&self, fact: &SensorFact) -> String;

    /// Decompress the wire text format back to a SensorFact.
    pub fn decompress(&self, s: &str) -> Result<SensorFact, OsError>;

    /// Encode float with fixed-point precision to Base62.
    pub fn encode_b62(&self, n: f64, use_precision: bool) -> String;

    /// Decode Base62 string to float.
    pub fn decode_b62(&self, s: &str, use_precision: bool) -> Result<f64, OsError>;

    /// Compress a unit string to its compact token form.
    /// Returns "Z" for unknown units.
    fn compress_unit(&self, unit_str: &str) -> String;

    fn split_coeff_attr_power(p: &str) -> (Option<f64>, String, String);
    fn strip_sym_and_power(sym_p: &str) -> (String, String);
}
```

### 7.1 Timestamp Encoding

```rust
/// Encode a millisecond timestamp to URL-safe Base64 (6 bytes, no padding).
fn encode_timestamp(ts_ms: u64) -> String {
    let bytes = ts_ms.to_be_bytes();          // 8-byte big-endian
    let six_bytes = &bytes[2..];              // take 6 LSBs
    base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(six_bytes)
}

/// Decode URL-safe Base64 timestamp back to u64.
fn decode_timestamp(ts_b64: &str) -> Result<u64, OsError> {
    let mut padded = ts_b64.to_string();
    while padded.len() % 4 != 0 { padded.push('='); }
    let bytes = base64::engine::general_purpose::URL_SAFE.decode(&padded)?;
    // zero-extend to 8 bytes
    let mut buf = [0u8; 8];
    let src = &bytes[..bytes.len().min(6)];
    buf[8 - src.len()..].copy_from_slice(src);
    Ok(u64::from_be_bytes(buf))
}
```

### 7.2 Wire Format String Grammar

```
compressed_str = header "|" sensor_segments extras
header         = device_id "." state_sym "." ts_b64url
sensor_segment = sensor_id ">" state_sym "." unit_token ":" value_b62 "|"
extras         = ["&" geohash "|"] ["#" url_b64 "|"] ["@" msg_b64]
unit_token     = part ("/" part)*
part           = [coeff_b62 ","] sym_code [power_digit]
```

---

## 8. Module: `fusion`

**File:** `src/fusion.rs`  
**Maps from:** `pycore/unified_parser.py`

### 8.1 Core Types

```rust
/// Per-device template registry entry (in-memory)
struct RegistryEntry {
    data:         DeviceRegistry,
    path:         PathBuf,
    dirty:        bool,
    runtime_vals: HashMap<String, Vec<Vec<u8>>>,  // tid → [slot_bytes]
    sig_index:    HashMap<String, String>,          // sig → tid
}

#[derive(Debug, Default, Clone, serde::Serialize, serde::Deserialize)]
pub struct DeviceRegistry {
    pub aid:       String,
    pub templates: HashMap<String, TemplateEntry>,
}

#[derive(Debug, Default, Clone, serde::Serialize, serde::Deserialize)]
pub struct TemplateEntry {
    pub sig:            String,
    pub last_vals_bin:  Vec<String>,   // Base64-encoded slot values
}
```

### 8.2 FusionEngine

```rust
pub struct FusionEngine {
    local_id:      u32,
    local_id_str:  String,
    root_dir:      PathBuf,
    codec:         Base62Codec,
    ram_cache:     parking_lot::RwLock<HashMap<String, Arc<parking_lot::RwLock<RegistryEntry>>>>,
    // Injected externally after construction:
    // protocol: Option<Arc<HandshakeManager>>  (set via set_protocol())
    protocol:      Option<Arc<HandshakeManager>>,
}

impl FusionEngine {
    pub fn new(config: &OsConfig, base_dir: &Path) -> Result<Self, OsError>;

    /// Set the local device ID (called after ID assignment).
    pub fn set_local_id(&mut self, id: u32);

    /// Inject the HandshakeManager reference (wired by node orchestrator).
    pub fn set_protocol(&mut self, protocol: Arc<HandshakeManager>);

    // ── Encode path ──────────────────────────────────────────────────

    /// Encode "{aid};{compressed_str}" to a binary BinaryFrame.
    ///
    /// strategy: EncodeStrategy::Full | EncodeStrategy::Diff
    pub fn run_engine(&self, raw_input: &[u8], strategy: EncodeStrategy) -> Result<BinaryFrame, OsError>;

    // ── Decode path ──────────────────────────────────────────────────

    /// Decode a binary BinaryFrame back to a SensorFact with metadata.
    pub fn decompress(&self, packet: &[u8]) -> Result<(SensorFact, PacketMeta), OsError>;

    // ── Internal helpers ─────────────────────────────────────────────

    fn auto_decompose(raw_input: &[u8]) -> Option<Decomposed>;
    fn decompose_for_receive(raw_input: &str) -> Option<(String, Vec<Vec<u8>>)>;
    fn get_active_registry(&self, aid: u32) -> Arc<parking_lot::RwLock<RegistryEntry>>;
    fn sync_to_disk(&self, aid: u32) -> Result<(), OsError>;
    fn finalize_bin(
        &self,
        cmd:       u8,
        tid:       u8,
        ts_str:    &str,
        body:      &[u8],
        route_ids: &[u32],
        src_aid:   u32,
    ) -> Result<BinaryFrame, OsError>;
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EncodeStrategy { Full, Diff }

struct Decomposed {
    ts_str:    String,
    sig:       String,
    vals_bin:  Vec<Vec<u8>>,
    src_aid:   u32,
    route_ids: Vec<u32>,
}
```

### 8.3 `finalize_bin` Binary Frame Assembly

```rust
fn finalize_bin(...) -> Result<BinaryFrame, OsError> {
    let r_bin: Vec<u8> = route_ids.iter()
        .flat_map(|id| id.to_be_bytes())
        .collect();
    let route_count = route_ids.len() as u8;

    // Decode ts_str (URL-safe Base64) → 6 bytes
    let ts_raw = decode_ts_token(ts_str)?;

    // Encryption decision
    let (secure_enabled, session_key) = self.resolve_outbound_security(src_aid);
    let wire_cmd = if secure_enabled {
        secure_variant_cmd(cmd)
    } else { cmd };

    // CRC-8 over plaintext body
    let crc8_val = crc8(body);
    let body_len = body.len();
    let frame_len = 2 + r_bin.len() + 7 + body_len + 1 + 2;
    let mut frame = vec![0u8; frame_len];

    frame[0] = wire_cmd;
    frame[1] = route_count;
    frame[2..2 + r_bin.len()].copy_from_slice(&r_bin);
    let tid_off = 2 + r_bin.len();
    frame[tid_off] = tid;
    frame[tid_off + 1..tid_off + 7].copy_from_slice(&ts_raw);
    let body_off = tid_off + 7;

    if secure_enabled {
        xor_payload_into(body, &session_key.unwrap(), (crc8_val & 0x1F) as u32,
                         &mut frame[body_off..body_off + body_len]);
    } else {
        frame[body_off..body_off + body_len].copy_from_slice(body);
    }

    let crc8_off = body_off + body_len;
    frame[crc8_off] = crc8_val;
    let crc16_val = crc16_ccitt(&frame[..crc8_off + 1]);
    frame[crc8_off + 1..].copy_from_slice(&crc16_val.to_be_bytes());

    Ok(BinaryFrame(bytes::Bytes::from(frame)))
}
```

### 8.4 Registry Sharding

```rust
/// Get the disk path for a device registry file.
/// Mirrors Python: get_registry_path(aid)
pub fn get_registry_path(root_dir: &Path, aid: u32) -> PathBuf {
    let padded = format!("{:010}", aid);
    root_dir
        .join(&padded[0..2])
        .join(&padded[2..4])
        .join(format!("{}.json", aid))
}
```

---

## 9. Module: `handshake`

**File:** `src/handshake.rs`  
**Maps from:** `pycore/handshake.py`

### 9.1 CMD Constants

```rust
pub mod cmd {
    pub const DATA_FULL:           u8 = 0x3F;
    pub const DATA_FULL_SEC:       u8 = 0x40;
    pub const DATA_DIFF:           u8 = 0xAA;
    pub const DATA_DIFF_SEC:       u8 = 0xAB;
    pub const DATA_HEART:          u8 = 0x7F;
    pub const DATA_HEART_SEC:      u8 = 0x80;
    pub const ID_REQUEST:          u8 = 0x01;
    pub const ID_ASSIGN:           u8 = 0x02;
    pub const ID_POOL_REQ:         u8 = 0x03;
    pub const ID_POOL_RES:         u8 = 0x04;
    pub const HANDSHAKE_ACK:       u8 = 0x05;
    pub const HANDSHAKE_NACK:      u8 = 0x06;
    pub const PING:                u8 = 0x09;
    pub const PONG:                u8 = 0x0A;
    pub const TIME_REQUEST:        u8 = 0x0B;
    pub const TIME_RESPONSE:       u8 = 0x0C;
    pub const SECURE_DICT_READY:   u8 = 0x0D;
    pub const SECURE_CHANNEL_ACK:  u8 = 0x0E;

    pub fn is_data_cmd(cmd: u8)         -> bool { matches!(cmd, DATA_FULL | DATA_FULL_SEC | DATA_DIFF | DATA_DIFF_SEC | DATA_HEART | DATA_HEART_SEC) }
    pub fn is_secure_data_cmd(cmd: u8)  -> bool { matches!(cmd, DATA_FULL_SEC | DATA_DIFF_SEC | DATA_HEART_SEC) }
    pub fn is_ctrl_cmd(cmd: u8)         -> bool { matches!(cmd, ID_REQUEST..=HANDSHAKE_NACK | PING | PONG | TIME_REQUEST | TIME_RESPONSE | SECURE_DICT_READY | SECURE_CHANNEL_ACK) }

    /// Map secure CMD → plain CMD
    pub fn normalize(cmd: u8) -> u8 { match cmd { DATA_FULL_SEC => DATA_FULL, DATA_DIFF_SEC => DATA_DIFF, DATA_HEART_SEC => DATA_HEART, other => other } }
    /// Map plain CMD → secure CMD
    pub fn secure_variant(cmd: u8) -> u8 { match cmd { DATA_FULL => DATA_FULL_SEC, DATA_DIFF => DATA_DIFF_SEC, DATA_HEART => DATA_HEART_SEC, other => other } }
}
```

### 9.2 SecureSession

```rust
#[derive(Debug, Clone)]
pub struct SecureSession {
    pub last:               u64,             // UNIX timestamp of last access
    pub peer_addr:          Option<String>,
    pub first_plaintext_ts: Option<u64>,
    pub pending_timestamp:  Option<u64>,
    pub pending_key:        Option<[u8; 32]>,
    pub key:                Option<[u8; 32]>,
    pub dict_ready:         bool,
    pub decrypt_confirmed:  bool,
    pub state:              SessionState,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SessionState { Init, PlaintextSent, DictReady, Secure }
```

### 9.3 HandshakeManager

```rust
pub struct HandshakeManager {
    target_sync_count: u32,
    expire_seconds:    u64,
    registry_status:   parking_lot::Mutex<HashMap<String, SyncEntry>>,
    secure_sessions:   parking_lot::Mutex<HashMap<String, SecureSession>>,
    seq_counter:       AtomicU16,
    pub id_allocator:  Option<Arc<dyn IdAllocator>>,   // injected
    pub parser:        Option<Arc<FusionEngine>>,       // injected
    pub min_valid_timestamp: u64,
    pub last_server_time:    AtomicU64,
}

#[derive(Debug, Clone)]
struct SyncEntry {
    count: u32,
    last:  u64,
    state: SyncState,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SyncState { Handshaking, Synced }

impl HandshakeManager {
    pub fn new(target_sync_count: u32, expire_seconds: u64) -> Self;

    // ── Inbound packet routing ────────────────────────────────────

    /// Parse CMD byte and route to the appropriate handler.
    pub fn classify_and_dispatch(&self, packet: &[u8], addr: Option<&str>) -> HandshakeResult;

    // ── Strategy management ───────────────────────────────────────

    /// Decide FULL_PACKET vs DIFF_PACKET for outbound encoding.
    pub fn get_strategy(&self, aid: u32, has_template: bool) -> TransmitStrategy;

    /// Increment successful-send counter for a device.
    pub fn commit_success(&self, aid: u32);

    // ── Session security ──────────────────────────────────────────

    pub fn note_local_plaintext_sent(&self, aid: u32, ts_raw: u64, addr: Option<&str>);
    pub fn establish_remote_plaintext(&self, aid: u32, ts_raw: u64, addr: Option<&str>);
    pub fn confirm_secure_dict(&self, aid: u32, ts_raw: Option<u64>, addr: Option<&str>) -> bool;
    pub fn mark_secure_channel(&self, aid: u32, addr: Option<&str>);
    pub fn has_secure_dict(&self, aid: u32) -> bool;
    pub fn should_encrypt_outbound(&self, aid: u32) -> bool;
    pub fn get_session_key(&self, aid: u32) -> Option<[u8; 32]>;
    pub fn note_server_time(&self, ts: u64);

    // ── Packet builders ───────────────────────────────────────────

    pub fn build_id_request(&self, device_meta: &serde_json::Value) -> bytes::Bytes;
    pub fn build_id_pool_request(&self, count: u16, meta: &serde_json::Value) -> bytes::Bytes;
    pub fn build_ping(&self) -> bytes::Bytes;
    pub fn build_time_request(&self) -> bytes::Bytes;

    // Internal packet builders
    fn build_id_assign(seq: u16, aid: u32) -> bytes::Bytes;
    fn build_id_pool_response(seq: u16, pool: &[u32]) -> bytes::Bytes;
    fn build_ack(seq: u16) -> bytes::Bytes;
    fn build_nack(seq: u16, reason: &str) -> bytes::Bytes;
    fn build_pong(seq: u16) -> bytes::Bytes;
    fn build_time_response(seq: u16, server_time: u64) -> bytes::Bytes;
    fn build_secure_dict_ready(aid: u32, ts: u64) -> bytes::Bytes;
    fn build_secure_channel_ack(aid: u32) -> bytes::Bytes;

    // ── Transport-level handshake loops ───────────────────────────

    pub fn request_id_via_transport<S, R>(
        &self,
        send:        S,
        recv:        R,
        device_meta: &serde_json::Value,
        timeout_ms:  u64,
    ) -> Result<u32, OsError>
    where
        S: Fn(&[u8]) -> Result<(), OsError>,
        R: Fn(u64) -> Result<Option<bytes::Bytes>, OsError>;   // timeout_ms

    pub fn request_id_pool_via_transport<S, R>(
        &self, send: S, recv: R, count: u16, meta: &serde_json::Value, timeout_ms: u64,
    ) -> Result<Vec<u32>, OsError>
    where S: Fn(&[u8]) -> Result<(), OsError>, R: Fn(u64) -> Result<Option<bytes::Bytes>, OsError>;

    pub fn request_time_via_transport<S, R>(
        &self, send: S, recv: R, timeout_ms: u64,
    ) -> Result<u64, OsError>
    where S: Fn(&[u8]) -> Result<(), OsError>, R: Fn(u64) -> Result<Option<bytes::Bytes>, OsError>;

    // ── Private helpers ───────────────────────────────────────────

    fn next_seq(&self) -> u16;          // wrapping u16 counter
    fn normalize_aid(aid: u32) -> String;
    fn cleanup_expired(&self);
}
```

### 9.4 `IdAllocator` Trait

```rust
pub trait IdAllocator: Send + Sync {
    fn allocate_id(&self, meta: Option<&serde_json::Value>) -> Result<u32, OsError>;
    fn allocate_pool(&self, count: u16, meta: Option<&serde_json::Value>) -> Result<Vec<u32>, OsError>;
    fn release_id(&self, id: u32) -> bool;
    fn is_allocated(&self, id: u32) -> bool;
}
```

---

## 10. Module: `transport`

**File:** `src/transport.rs`  
**Maps from:** `pycore/transporter_manager.py` + driver interfaces

### 10.1 Transporter Trait

```rust
pub trait Transporter: Send + Sync {
    /// Send a binary packet. Returns true on success.
    fn send(&self, payload: &[u8], config: &OsConfig) -> bool;

    /// Optional: start a background receive loop.
    fn listen(&self, _config: &OsConfig, _callback: Arc<dyn Fn(&[u8], Option<&str>) + Send + Sync>) -> Result<(), OsError> {
        Err(OsError::NotSupported("listen".into()))
    }

    fn name(&self) -> &str;
}
```

### 10.2 TransportKind

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum TransportKind {
    Application,   // MQTT, etc.
    Transport,     // UDP, TCP, QUIC
    Physical,      // UART, RS-485, CAN, LoRa
}
```

### 10.3 TransporterRegistry

```rust
pub struct TransporterRegistry {
    drivers: parking_lot::RwLock<HashMap<String, (Arc<dyn Transporter>, TransportKind)>>,
}

impl TransporterRegistry {
    pub fn new() -> Self;
    pub fn register(&self, name: &str, driver: Arc<dyn Transporter>, kind: TransportKind);
    pub fn get(&self, name: &str) -> Option<Arc<dyn Transporter>>;
    pub fn list(&self) -> Vec<String>;
}
```

---

## 11. Module: `node` (Orchestrator)

**File:** `src/node.rs`  
**Maps from:** `pycore/core.py`

```rust
pub struct OpenSynapticNode {
    pub config:           OsConfig,
    pub config_path:      PathBuf,
    pub base_dir:         PathBuf,
    pub assigned_id:      Option<u32>,
    pub device_id:        String,
    pub standardizer:     Standardizer,
    pub engine:           SolidityEngine,
    pub fusion:           Arc<FusionEngine>,
    pub protocol:         Arc<HandshakeManager>,
    pub transporters:     TransporterRegistry,
}

impl OpenSynapticNode {
    /// Construct from a Config.json path.
    pub fn new(config_path: &Path) -> Result<Self, OsError>;

    /// Auto-detect Config.json by walking up from the executable's directory.
    pub fn auto_detect() -> Result<Self, OsError>;

    // ── ID management ─────────────────────────────────────────────

    /// Request a device ID from the server (UDP).
    pub fn ensure_id(
        &mut self,
        server_ip:   &str,
        server_port: u16,
        device_meta: Option<&serde_json::Value>,
        timeout_ms:  u64,
    ) -> Result<bool, OsError>;

    pub fn is_id_missing(&self) -> bool {
        matches!(self.assigned_id, None | Some(0) | Some(u32::MAX))
    }

    // ── Time sync ─────────────────────────────────────────────────

    pub fn ensure_time(
        &mut self,
        server_ip:   Option<&str>,
        server_port: Option<u16>,
        timeout_ms:  u64,
    ) -> Result<Option<u64>, OsError>;

    // ── Main pipeline ─────────────────────────────────────────────

    /// Full pipeline: standardize → compress → fuse → return binary frame.
    ///
    /// sensors: Vec<(sensor_id, status, raw_value, unit_str)>
    /// Raises OsError::IdNotAssigned if no valid ID.
    pub fn transmit(
        &self,
        sensors:       &[(String, String, f64, String)],
        device_id:     Option<&str>,
        device_status: &str,
        timestamp:     Option<u64>,
        extras:        Option<SensorExtras>,
    ) -> Result<TransmitResult, OsError>;

    // ── Send / Receive ────────────────────────────────────────────

    pub fn dispatch(&self, frame: &BinaryFrame, medium: Option<&str>) -> bool;

    pub fn receive(&self, packet: &[u8]) -> Result<SensorFact, OsError>;

    pub fn receive_via_protocol(&self, packet: &[u8], addr: Option<&str>) -> HandshakeResult;

    /// UDP send + single reply receive.
    pub fn dispatch_with_reply(
        &self,
        frame:       &BinaryFrame,
        server_ip:   Option<&str>,
        server_port: Option<u16>,
        timeout_ms:  u64,
    ) -> Result<Option<bytes::Bytes>, OsError>;

    // ── Config persistence ────────────────────────────────────────

    pub fn save_config(&self) -> Result<(), OsError>;

    pub fn reload_config(&mut self) -> Result<(), OsError>;
}
```

### 11.1 `transmit` internal pipeline

```rust
pub fn transmit(...) -> Result<TransmitResult, OsError> {
    if self.is_id_missing() {
        return Err(OsError::IdNotAssigned(self.device_id.clone()));
    }
    let aid = self.assigned_id.unwrap();
    let ts = timestamp.unwrap_or_else(|| unix_now_secs());

    // Stage 1: Standardize
    let fact = self.standardizer.standardize(device_id, device_status, sensors, Some(ts), extras);

    // Stage 2: Compress
    let compressed = self.engine.compress(&fact);
    let raw_input = format!("{};{}", aid, compressed);

    // Stage 3: Strategy selection
    let reg = self.fusion.get_active_registry(aid);
    let has_template = !reg.read().data.templates.is_empty();
    let strategy = self.protocol.get_strategy(aid, has_template);
    let encode_strategy = match strategy {
        TransmitStrategy::FullPacket => EncodeStrategy::Full,
        TransmitStrategy::DiffPacket => EncodeStrategy::Diff,
    };

    // Stage 4: Fuse to binary
    let frame = self.fusion.run_engine(raw_input.as_bytes(), encode_strategy)?;

    // Post-flight
    self.protocol.commit_success(aid);

    Ok(TransmitResult { frame, aid, strategy })
}
```

---

## 12. PyO3 Bindings Layer

**File:** `src/py_bindings.rs`

```rust
use pyo3::prelude::*;

/// Register the rscore Python extension module.
#[pymodule]
fn rscore(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<PyOpenSynapticNode>()?;
    m.add_class::<PyStandardizer>()?;
    m.add_class::<PySolidityEngine>()?;
    m.add_class::<PyFusionEngine>()?;
    m.add_class::<PyHandshakeManager>()?;
    Ok(())
}

/// Python-callable wrapper for OpenSynapticNode.
#[pyclass(name = "OpenSynaptic")]
pub struct PyOpenSynapticNode {
    inner: OpenSynapticNode,
}

#[pymethods]
impl PyOpenSynapticNode {
    #[new]
    fn new(config_path: Option<String>) -> PyResult<Self>;

    fn ensure_id(&mut self, server_ip: &str, server_port: u16,
                 device_meta: Option<&PyDict>, timeout: Option<f64>) -> PyResult<bool>;

    fn ensure_time(&mut self, server_ip: Option<&str>, server_port: Option<u16>,
                   timeout: Option<f64>) -> PyResult<Option<u64>>;

    fn transmit(&self, sensors: Vec<(String, String, f64, String)>,
                device_id: Option<&str>, device_status: Option<&str>) -> PyResult<(PyObject, u32, String)>;
    // Returns (bytes, aid, strategy_str) matching pycore tuple

    fn dispatch(&self, packet: &PyBytes, medium: Option<&str>) -> PyResult<bool>;

    fn receive(&self, raw_bytes: &PyBytes) -> PyResult<PyObject>;  // → Python dict

    fn receive_via_protocol(&self, raw_bytes: &PyBytes,
                            addr: Option<&str>) -> PyResult<PyObject>;  // → Python dict
}
```

**Type mappings from Rust → Python:**

| Rust type | Python type |
|---|---|
| `BinaryFrame` | `bytes` |
| `SensorFact` | `dict` (matching pycore fact structure) |
| `HandshakeResult` | `dict` with `type`, `cmd`, `result`, `response` keys |
| `TransmitStrategy::FullPacket` | `"FULL_PACKET"` |
| `TransmitStrategy::DiffPacket` | `"DIFF_PACKET"` |
| `OsError` | `RuntimeError` with message string |

---

## 13. Config Mapping

**File:** `src/config.rs`

```rust
#[derive(Debug, Clone, serde::Deserialize, Default)]
pub struct OsConfig {
    #[serde(rename = "VERSION")]
    pub version:             String,
    pub assigned_id:         Option<u32>,
    pub device_id:           String,
    #[serde(rename = "OpenSynaptic_Setting")]
    pub settings:            OsSettings,
    #[serde(rename = "Server_Core")]
    pub server_core:         ServerCore,
    #[serde(rename = "Client_Core")]
    pub client_core:         ClientCore,
    #[serde(rename = "RESOURCES")]
    pub resources:           Resources,
    pub engine_settings:     EngineSettings,
    pub security_settings:   SecuritySettings,
    pub payload_switches:    PayloadSwitches,
}

#[derive(Debug, Clone, serde::Deserialize, Default)]
pub struct EngineSettings {
    pub precision:              u8,
    pub lock_threshold:         u32,
    pub active_standardization: bool,
    pub active_compression:     bool,
    pub active_collapse:        bool,
    pub use_ms:                 bool,
    pub zero_copy_transport:    bool,
    pub time_sync_threshold:    u64,
    pub epoch_base:             u64,
}

#[derive(Debug, Clone, serde::Deserialize, Default)]
pub struct SecuritySettings {
    pub time_sync_threshold:           u64,
    pub drop_on_crc16_failure:         bool,
    pub secure_session_expire_seconds: u64,
}

#[derive(Debug, Clone, serde::Deserialize, Default)]
pub struct Resources {
    pub root:                 Option<String>,
    pub registry:             Option<String>,
    pub symbols:              Option<String>,
    pub prefixes:             Option<String>,
    pub transport_status:     HashMap<String, bool>,
    pub physical_status:      HashMap<String, bool>,
    pub application_status:   HashMap<String, bool>,
    pub transporters_status:  HashMap<String, bool>,
    pub transport_config:     HashMap<String, serde_json::Value>,
    pub physical_config:      HashMap<String, serde_json::Value>,
    pub application_config:   HashMap<String, serde_json::Value>,
}

impl OsConfig {
    pub fn from_file(path: &Path) -> Result<Self, OsError>;
    pub fn save_to_file(&self, path: &Path) -> Result<(), OsError>;
}
```

---

## 14. Error Types

**File:** `src/error.rs`

```rust
#[derive(Debug, thiserror::Error)]
pub enum OsError {
    #[error("ID not assigned for device '{0}'")]
    IdNotAssigned(String),

    #[error("CRC-16 mismatch")]
    Crc16Mismatch,

    #[error("CRC-8 mismatch")]
    Crc8Mismatch,

    #[error("Packet too short: {0} bytes")]
    PacketTooShort(usize),

    #[error("Template {0} missing")]
    TemplateMissing(String),

    #[error("No cached values for TID={0}")]
    NoCachedValues(String),

    #[error("Missing secure key for aid={0}")]
    MissingSecureKey(u32),

    #[error("Base62 decode error: {0}")]
    Base62Decode(String),

    #[error("Unit not found: '{0}'")]
    UnitNotFound(String),

    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Base64 error: {0}")]
    Base64(#[from] base64::DecodeError),

    #[error("Not supported: {0}")]
    NotSupported(String),

    #[error("Timeout after {0}ms")]
    Timeout(u64),

    #[error("Transport send failed: {0}")]
    TransportSend(String),

    #[error("ID pool exhausted")]
    IdPoolExhausted,

    #[error("{0}")]
    Other(String),
}
```

---

## 15. Thread-Safety Model

| Component | Rust Mechanism | Notes |
|---|---|---|
| `FusionEngine._RAM_CACHE` | `RwLock<HashMap>` | Multiple readers, single writer on registry load |
| Per-device `RegistryEntry` | `Arc<RwLock<RegistryEntry>>` | Fine-grained per-device lock |
| `HandshakeManager.registry_status` | `Mutex<HashMap>` | Commit / strategy reads |
| `HandshakeManager.secure_sessions` | Same `Mutex` | Single lock covers both maps |
| `HandshakeManager.seq_counter` | `AtomicU16` | Lock-free rolling counter |
| `HandshakeManager.last_server_time` | `AtomicU64` | Lock-free write |
| `TransporterRegistry` | `RwLock<HashMap>` | Fast parallel send lookups |
| `Standardizer.unit_cache` | `RwLock<HashMap>` | Fast read path for cached laws |

**Shared ownership model:** `Arc<HandshakeManager>` is cloned into both `FusionEngine` and `OpenSynapticNode`. The fusion engine accesses it read-only (key lookups / strategy check). Mutation of session state goes through the manager's own internal locks.

---

## 16. Implementation Notes & Divergences from PyCore

### 16.1 Native Library Policy

- **pycore** uses ctypes to call `os_base62.dll` / `os_security.dll`.
- **rscore** re-implements those algorithms natively in Rust — no external C ABI dependency.
- The `security::derive_session_key` function **must produce byte-identical output** to `os_derive_session_key` in `security_native.c` because sessions established by one core must be decryptable by the other.
- Add a cross-core test vector table in `tests/security_compat.rs`.

### 16.2 Zero-Copy Strategy

- Use `bytes::Bytes` (ref-counted, COW) for all frame data.
- The `BinaryFrame` wrapper is a newtype over `Bytes` — no allocation on clone.
- `FusionEngine::run_engine` writes into a `Vec<u8>` once, then freezes it via `Bytes::from(vec)`.
- `xor_payload_into` writes directly into the preallocated frame buffer.

### 16.3 Config.json Serialization

- Use `serde_json::Value` for dynamic/unknown keys (e.g. `transport_config`, `application_config`).
- `OsConfig::save_to_file` must preserve all unknown top-level keys to avoid stripping config added by plugins.  
  Strategy: deserialize into `serde_json::Map`, patch known fields, serialize back.

### 16.4 Registry Cache Invalidation

- pycore uses a thread-per-write `_sync_to_disk` flush. rscore should use a background tokio task that drains a dirty-set channel.
- `RegistryEntry.dirty` becomes `AtomicBool`; the disk-writer drains it via `compare_exchange`.

### 16.5 Timestamp Precision

- pycore uses `use_ms=true` (milliseconds) by default. rscore `unix_now_ms()` helper:

```rust
fn unix_now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}
```

### 16.6 Strategy Parity

The strategy logic must be **bit-for-bit compatible** with pycore so that a Rust node can be served by a Python server and vice versa.  
Specifically: `get_strategy` must return `DiffPacket` under the same conditions (template exists AND sync count ≥ target).

### 16.7 Base62 Charset

```
"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
   0-9 = 0-9
   a-z = 10-35
   A-Z = 36-61
```

This ordering is non-standard (differs from rfc4648). Must match exactly.

### 16.8 Fallback Behavior

pycore returns error dicts instead of raising. rscore returns `Result<_, OsError>`.  
The PyO3 layer converts `OsError` to Python `RuntimeError` / `ValueError` as appropriate:

| OsError variant | Python exception |
|---|---|
| `IdNotAssigned` | `RuntimeError` |
| `Crc16Mismatch`, `Crc8Mismatch` | `ValueError` |
| `TemplateMissing`, `NoCachedValues` | `KeyError` |
| `Json`, `Base62Decode` | `ValueError` |
| `Io` | `OSError` |
| `Timeout` | `TimeoutError` |
| everything else | `RuntimeError` |

---

## Appendix: Cross-Core Compatibility Test Vectors

These values must be identical between pycore and rscore:

| Test | Input | Expected Output |
|---|---|---|
| `crc8(b"abc")` | `[0x61, 0x62, 0x63]` | Must match `security_native.c` output |
| `crc16_ccitt(b"abc")` | same | Must match |
| `derive_session_key(42, 1700000000)` | `aid=42, ts=1700000000` | 32 bytes, identical |
| `b62_encode(12.3456, precision=4)` | `123456` as fixed-point | Must match `Base62Codec.encode(12.3456)` |
| `b62_decode(token, precision=4)` | reverse | `≈ 12.3456` |
| `compress(fact)` → `decompress(s)` | round-trip | lossless |
| `run_engine(raw, FULL)` → `decompress(frame)` | round-trip | lossless |
| `run_engine(raw1, DIFF)` after `run_engine(raw2, FULL)` | diff round-trip | lossless |

> Run: `python -u src/main.py plugin-test --suite component` alongside the Rust unit tests to confirm parity.

