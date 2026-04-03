# PYCORE → RSCORE Rust API Spec

This document defines the Rust-side API contract that must remain
behaviour-compatible with `src/opensynaptic/core/pycore/`.

---

## Implementation Status

| Stage | Description | Status |
|---|---|---|
| 1 – Shim | `rscore` plugin exports pycore-compatible Python symbols | ✅ Complete |
| 2 – Hybrid | Rust handles Base62 codec + CMD helpers; Python keeps orchestration | ✅ Complete |
| 3 – Native | Rust packet build/parse replaces Python hot loops with golden-vector parity | 🔲 Planned |

---

## Scope

- Keep `opensynaptic.core` public symbols unchanged.
- Allow `engine_settings.core_backend = "rscore"` opt-in without changing user code.
- Preserve command bytes and packet semantics used by `OSHandshakeManager`/`OSVisualFusionEngine`.

---

## Public Symbol Parity

The rscore plugin exposes the same symbol names as pycore:

| Symbol | Stage 2 implementation |
|---|---|
| `OpenSynaptic` | pycore shim |
| `OpenSynapticStandardizer` | pycore shim |
| `OpenSynapticEngine` | **hybrid** – `self.codec = RsBase62Codec` when DLL is present |
| `OSVisualFusionEngine` | pycore shim |
| `OSHandshakeManager` | pycore shim |
| `CMD` | pycore constant class (wire values frozen) |
| `TransporterManager` | pycore shim |

---

## Rust Crate

Location: `src/opensynaptic/core/rscore/rust/`

```
Cargo.toml          – cdylib, release profile O3+strip
src/lib.rs          – all C-ABI #[no_mangle] exports
```

Build output: `src/opensynaptic/utils/c/bin/os_rscore.dll` (Windows),
`os_rscore.so` (Linux), `os_rscore.dylib` (macOS).

---

## Implemented C-ABI Exports

These are the **live** symbols in `os_rscore` (stage 2):

```rust
// Base62 codec  (byte-for-byte identical semantics to base62_native.c)
pub unsafe extern "C" fn os_b62_encode_i64(value: i64, out: *mut c_char, out_len: usize) -> i32;
pub unsafe extern "C" fn os_b62_decode_i64(s: *const c_char, ok: *mut i32) -> i64;

// CMD byte helpers
pub extern "C" fn os_cmd_is_data(cmd: u8) -> i32;
pub extern "C" fn os_cmd_normalize_data(cmd: u8) -> u8;
pub extern "C" fn os_cmd_secure_variant(cmd: u8) -> u8;

// Metadata
pub unsafe extern "C" fn os_rscore_version(out: *mut c_char, out_len: usize) -> i32;
```

---

## Command Byte Contract (`CMD`)

Wire-level values are immutable. Any change is a **breaking protocol change**.

| Name | Value |
|---|---:|
| `DATA_FULL` | 63 |
| `DATA_FULL_SEC` | 64 |
| `DATA_DIFF` | 170 |
| `DATA_DIFF_SEC` | 171 |
| `DATA_HEART` | 127 |
| `DATA_HEART_SEC` | 128 |
| `ID_REQUEST` | 1 |
| `ID_ASSIGN` | 2 |
| `ID_POOL_REQ` | 3 |
| `ID_POOL_RES` | 4 |
| `HANDSHAKE_ACK` | 5 |
| `HANDSHAKE_NACK` | 6 |
| `PING` | 9 |
| `PONG` | 10 |
| `TIME_REQUEST` | 11 |
| `TIME_RESPONSE` | 12 |
| `SECURE_DICT_READY` | 13 |
| `SECURE_CHANNEL_ACK` | 14 |

---

## Python Bindings (`rscore/codec.py`)

```python
from opensynaptic.core.rscore.codec import (
    RsBase62Codec,     # drop-in for utils.base62.base62.Base62Codec
    has_rs_native,     # bool – DLL present?
    rs_version,        # str  – "opensynaptic_rscore/0.1.0"
    cmd_is_data,       # (int) -> bool
    cmd_normalize_data,# (int) -> int  secure→plain passthrough
    cmd_secure_variant,# (int) -> int  plain→secure passthrough
)
```

---

## Precision Contract

`RsBase62Codec(precision=p)` must encode/decode identically to
`Base62Codec(precision=p)` from `utils.base62.base62`.  
Golden-vector parity is enforced in `TestRscore.test_rs_codec_parity_with_c_codec`.

Precision is derived from `engine_settings.precision` (default 4 → `precision_val = 10000`).

---

## Rollout Stages (detailed)

### Stage 3 – Native (planned)

When implemented, the following Python hot loops will be replaced:

```rust
// Packet header build
pub fn os_parse_header(packet: &[u8]) -> Result<PacketHeader, OsError>;
pub fn os_build_header(aid: u32, status: u8, timestamp_ms: u64, out: &mut [u8]) -> Result<usize, OsError>;

// CRC helpers (already in os_security; migrate to os_rscore for single crate)
pub fn os_crc16_ccitt(data: &[u8], poly: u16, init: u16) -> u16;
```

---

## Developer Workflow

**Build Rust DLL:**
```powershell
# Standalone
python -u src/opensynaptic/core/rscore/build_rscore.py

# Via CLI
python -u src/main.py rscore-build

# Together with C targets
python -u src/main.py native-build --include-rscore
```

**Check Rust DLL status:**
```powershell
python -u src/main.py rscore-check
python -u src/main.py rscore-check --json
```

**Switch active core to rscore:**
```json
// Config.json
"engine_settings": { "core_backend": "rscore" }
```
Or set environment variable: `OPENSYNAPTIC_CORE=rscore`

**Run parity tests:**
```powershell
$env:PYTHONPATH="src;."
py -3 -m unittest opensynaptic.services.test_plugin.component_tests.TestRscore
py -3 -m unittest opensynaptic.services.test_plugin.component_tests.TestRscoreEngine
```

---

## Compatibility Rules

- `assigned_id == 4294967295` remains unassigned sentinel.
- Transporter keys are lowercase in all status maps.
- Timestamp encoding (`use_ms`, `time_precision`, `epoch_base`) must round-trip with pycore.
- `compress(fact)` output **must be byte-identical** between pycore and rscore engines.

---

## Validation Matrix

Before enabling `core_backend=rscore` in production:

| Check | Test class | Status |
|---|---|---|
| `rscore` discoverable by `CoreManager` | `TestCoreManager.test_rscore_discovered` | ✅ |
| `rscore` loadable by `CoreManager` | `TestCoreManager.test_rscore_loadable` | ✅ |
| `has_rs_native()` returns True after build | `TestRscore.test_has_rs_native_returns_true` | ✅ |
| `RsBase62Codec` round-trip | `TestRscore.test_rs_codec_roundtrip` | ✅ |
| Rust vs C Base62 byte-parity | `TestRscore.test_rs_codec_parity_with_c_codec` | ✅ |
| CMD `is_data` matches pycore sets | `TestRscore.test_cmd_is_data_*` | ✅ |
| CMD `normalize_data` matches `BASE_DATA_CMD` | `TestRscore.test_cmd_normalize_data_*` | ✅ |
| `RsEngine.codec` is `RsBase62Codec` | `TestRscoreEngine.test_rs_engine_codec_is_rust` | ✅ |
| precision preserved across engines | `TestRscoreEngine.test_rs_engine_precision_preserved` | ✅ |
| `compress()` output identical | `TestRscoreEngine.test_compress_output_identical` | ✅ |
| cross-engine decompress interop | `TestRscoreEngine.test_cross_engine_interop` | ✅ |
| No regression in concurrency smoke | `scripts/concurrency_smoke.py` | 🔲 manual |
