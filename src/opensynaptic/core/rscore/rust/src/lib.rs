//! OpenSynaptic RSCore – C-ABI native library.
//!
//! Exports the same symbols as the existing C libraries so that Python can
//! load this DLL through the existing `native_loader.py` / ctypes path.
//!
//! ABI-stable function signatures must remain identical to:
//!   - `src/opensynaptic/utils/base62/base62_native.c`  (Base62 codec)
//!   - CMD byte constants in `src/opensynaptic/core/pycore/handshake.py`

use std::ffi::c_char;
use std::fs;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
#[cfg(feature = "worker")]
use std::sync::mpsc::{sync_channel, SyncSender, Receiver};
use std::time::{SystemTime, UNIX_EPOCH};
use base64::Engine;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::cell::RefCell;
use bumpalo::Bump;
use smallvec::SmallVec;
#[cfg(feature = "python-module")]
use pyo3::prelude::*;

#[cfg(feature = "python-module")]
#[pyfunction]
fn abi_info_py() -> String {
    "opensynaptic_rscore c-api+pyo3".to_string()
}

#[cfg(feature = "python-module")]
#[pymodule]
fn opensynaptic_rscore(_py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(abi_info_py, m)?)?;
    Ok(())
}

// ── Prevent thin-LTO from dropping C-ABI symbols ─────────────────────
//
// Rust runs thin-LTO inside the compiler (LLVM ThinLTOCodeGenerator)
// *before* the external linker processes --export-dynamic-symbol or
// --undefined flags.  If a `#[no_mangle] pub extern "C"` function has
// no callers in Rust code (only called via ctypes/FFI), LLVM may
// internalize and eliminate it.
//
// Storing function addresses in a `#[used]` static tells LLVM the
// values are externally observable, which keeps the function bodies
// alive through LTO.
//
// See: <https://github.com/rust-lang/rust/issues/78292>
//
// We store `*const ()` instead of `usize` because Rust >= 1.94 forbids
// pointer-to-integer casts during const evaluation.  A thin wrapper
// provides the `Sync` impl required for statics.
#[repr(transparent)]
struct SymRef(*const ());
unsafe impl Sync for SymRef {}

#[used]
#[doc(hidden)]
static _OS_ABI_KEEP: [SymRef; 32] = [
    SymRef(os_b62_encode_i64 as *const ()),
    SymRef(os_b62_decode_i64 as *const ()),
    SymRef(os_crc8 as *const ()),
    SymRef(os_crc16_ccitt as *const ()),
    SymRef(os_crc16_ccitt_pub as *const ()),
    SymRef(os_xor_payload as *const ()),
    SymRef(os_derive_session_key as *const ()),
    SymRef(os_cmd_is_data as *const ()),
    SymRef(os_cmd_normalize_data as *const ()),
    SymRef(os_cmd_secure_variant as *const ()),
    SymRef(os_parse_header_min as *const ()),
    SymRef(os_auto_decompose_input as *const ()),
    SymRef(os_compressor_create_v1 as *const ()),
    SymRef(os_compressor_free_v1 as *const ()),
    SymRef(os_compress_fact_v1 as *const ()),
    SymRef(os_fusion_state_create_v1 as *const ()),
    SymRef(os_fusion_state_free_v1 as *const ()),
    SymRef(os_fusion_state_seed_v1 as *const ()),
    SymRef(os_fusion_state_apply_v1 as *const ()),
    SymRef(os_fusion_state_receive_apply_v1 as *const ()),
    SymRef(os_rscore_version as *const ()),
    SymRef(os_fusion_run_json_v1 as *const ()),
    SymRef(os_fusion_decompress_json_v1 as *const ()),
    SymRef(os_fusion_relay_json_v1 as *const ()),
    SymRef(os_node_ensure_id_json_v1 as *const ()),
    SymRef(os_node_transmit_json_v1 as *const ()),
    SymRef(os_node_dispatch_json_v1 as *const ()),
    SymRef(os_pipeline_batch_v1 as *const ()),
    SymRef(os_standardize_json_v1 as *const ()),
    SymRef(os_handshake_negotiate_v1 as *const ()),
    SymRef(os_transporter_send_v1 as *const ()),
    SymRef(os_transporter_listen_v1 as *const ()),
];

#[cfg(feature = "worker")]
#[used]
#[doc(hidden)]
static _OS_ABI_KEEP_WORKER: [SymRef; 3] = [
    SymRef(os_worker_create_v1 as *const ()),
    SymRef(os_worker_submit_v1 as *const ()),
    SymRef(os_worker_destroy_v1 as *const ()),
];

fn push_u32_be(dst: &mut Vec<u8>, n: usize) -> Option<()> {
    let v = u32::try_from(n).ok()?;
    dst.extend_from_slice(&v.to_be_bytes());
    Some(())
}


fn read_u8(src: &[u8], off: &mut usize) -> Option<u8> {
    let b = *src.get(*off)?;
    *off += 1;
    Some(b)
}

fn read_u32_be(src: &[u8], off: &mut usize) -> Option<u32> {
    let bytes = src.get(*off..(*off + 4))?;
    *off += 4;
    Some(u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
}

fn read_f64_be(src: &[u8], off: &mut usize) -> Option<f64> {
    let bytes = src.get(*off..(*off + 8))?;
    *off += 8;
    Some(f64::from_be_bytes([
        bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
    ]))
}

fn read_string(src: &[u8], off: &mut usize) -> Option<String> {
    let len = read_u32_be(src, off)? as usize;
    let bytes = src.get(*off..(*off + len))?;
    *off += len;
    String::from_utf8(bytes.to_vec()).ok()
}

fn read_opt_string(src: &[u8], off: &mut usize) -> Option<Option<String>> {
    let len = read_u32_be(src, off)?;
    if len == u32::MAX {
        return Some(None);
    }
    let len = len as usize;
    let bytes = src.get(*off..(*off + len))?;
    *off += len;
    Some(Some(String::from_utf8(bytes.to_vec()).ok()?))
}

fn b62_encode_i64_string(value: i64) -> String {
    if value == 0 {
        return "0".to_string();
    }
    let neg = value < 0;
    let mut n: u64 = if neg { value.unsigned_abs() } else { value as u64 };
    let mut tmp = [0u8; 96];
    let mut idx = 0usize;
    while n > 0 && idx < tmp.len() - 1 {
        tmp[idx] = B62[(n % 62) as usize];
        n /= 62;
        idx += 1;
    }
    let mut out = String::with_capacity(idx + usize::from(neg));
    if neg {
        out.push('-');
    }
    while idx > 0 {
        idx -= 1;
        out.push(tmp[idx] as char);
    }
    out
}

fn py_round_ties_even_to_i64(x: f64) -> i64 {
    if !x.is_finite() {
        return 0;
    }
    let floor = x.floor();
    let frac = x - floor;
    let lower = floor as i64;
    const EPS: f64 = 1e-12;
    if frac < 0.5 - EPS {
        lower
    } else if frac > 0.5 + EPS {
        lower + 1
    } else if lower % 2 == 0 {
        lower
    } else {
        lower + 1
    }
}

fn encode_b62_num(n: f64, precision_val: i64, use_precision: bool) -> String {
    let normalized = if use_precision {
        py_round_ties_even_to_i64(n * precision_val as f64)
    } else if n >= 0.0 {
        n.trunc() as i64
    } else {
        n.ceil() as i64
    };
    b62_encode_i64_string(normalized)
}

fn b62_decode_i64_string(s: &str) -> Option<i64> {
    let bytes = s.as_bytes();
    if bytes.is_empty() {
        return None;
    }
    let (neg, digits) = if bytes[0] == b'-' {
        (true, &bytes[1..])
    } else {
        (false, bytes)
    };
    if digits.is_empty() {
        return None;
    }
    let mut val: i64 = 0;
    for &b in digits {
        let d: i64 = if b.is_ascii_digit() {
            (b - b'0') as i64
        } else if b.is_ascii_lowercase() {
            10 + (b - b'a') as i64
        } else if b.is_ascii_uppercase() {
            36 + (b - b'A') as i64
        } else {
            return None;
        };
        val = val.checked_mul(62)?.checked_add(d)?;
    }
    if neg {
        Some(-val)
    } else {
        Some(val)
    }
}

fn b62_decode_num(s: &str, precision_val: i64, use_precision: bool) -> Option<f64> {
    let raw = b62_decode_i64_string(s)?;
    if use_precision {
        Some((raw as f64) / (precision_val as f64))
    } else {
        Some(raw as f64)
    }
}

fn b64_urlsafe_decode_nopad(input: &str) -> Option<Vec<u8>> {
    base64::engine::general_purpose::URL_SAFE_NO_PAD.decode(input.as_bytes()).ok()
}

/// ② Decode 8-char base64url timestamp token → 6-byte array on the stack; zero heap allocation.
fn decode_ts_token_to_6bytes(ts_token: &str) -> Option<[u8; 6]> {
    let mut ts6 = [0u8; 6];
    let n = base64::engine::general_purpose::URL_SAFE_NO_PAD
        .decode_slice(ts_token.as_bytes(), &mut ts6)
        .ok()?;
    if n == 6 { Some(ts6) } else { None }
}

fn finalize_packet(cmd: u8, src_aid: u32, tid: u32, ts_token: &str, body: &[u8]) -> Option<Vec<u8>> {
    let tid_u8 = u8::try_from(tid).ok()?;
    let ts6 = decode_ts_token_to_6bytes(ts_token)?;
    let route_count = 1u8;
    let mut out = Vec::with_capacity(2 + 4 + 1 + 6 + body.len() + 1 + 2);
    out.push(cmd);
    out.push(route_count);
    out.extend_from_slice(&src_aid.to_be_bytes());
    out.push(tid_u8);
    out.extend_from_slice(&ts6);
    out.extend_from_slice(body);
    let crc8 = crc8_inner(body, 0x07, 0x00);
    out.push(crc8);
    let crc16 = crc16_ccitt(&out, CRC16_POLY, CRC16_INIT);
    out.extend_from_slice(&crc16.to_be_bytes());
    Some(out)
}

fn parse_compressed_payload_to_json(payload: &str, precision_val: i64) -> serde_json::Value {
    let mut out = serde_json::Map::new();
    let mut split = payload.split('@');
    let main = split.next().unwrap_or("");
    let msg = split.next();
    let segs: Vec<&str> = main.split('|').filter(|s| !s.is_empty()).collect();
    if segs.is_empty() {
        return serde_json::Value::Object(out);
    }

    let head: Vec<&str> = segs[0].split('.').collect();
    if head.len() >= 2 {
        out.insert("id".to_string(), serde_json::Value::String(head[0].to_string()));
        out.insert("s".to_string(), serde_json::Value::String(head[1].to_string()));
        if head.len() >= 3 {
            if let Some(ts6) = decode_ts_token_to_6bytes(head[2]) {
                let mut ts8 = [0u8; 8];
                ts8[2..8].copy_from_slice(&ts6);
                let ts_raw = u64::from_be_bytes(ts8);
                out.insert(
                    "t_raw".to_string(),
                    serde_json::Value::Number(serde_json::Number::from(ts_raw)),
                );
            }
        }
    }

    let mut idx = 1usize;
    for seg in segs.iter().skip(1) {
        if seg.starts_with('&') {
            out.insert("geohash".to_string(), serde_json::Value::String(seg[1..].to_string()));
            continue;
        }
        if seg.starts_with('#') {
            if let Ok(url_raw) = base64::engine::general_purpose::URL_SAFE_NO_PAD.decode(seg[1..].as_bytes()) {
                if let Ok(url_tail) = String::from_utf8(url_raw) {
                    out.insert("url".to_string(), serde_json::Value::String(format!("https://{}", url_tail)));
                }
            }
            continue;
        }
        if let Some((sid, rest)) = seg.split_once('>') {
            let (meta, v_enc) = match rest.rsplit_once(':') {
                Some(v) => v,
                None => continue,
            };
            let (sst, unit_enc) = match meta.split_once('.') {
                Some(v) => v,
                None => (meta, ""),
            };
            let value = b62_decode_num(v_enc, precision_val, true).unwrap_or(0.0);
            out.insert(format!("s{}_id", idx), serde_json::Value::String(sid.to_string()));
            out.insert(format!("s{}_s", idx), serde_json::Value::String(sst.to_string()));
            out.insert(format!("s{}_u", idx), serde_json::Value::String(unit_enc.to_string()));
            out.insert(
                format!("s{}_v", idx),
                serde_json::Value::Number(
                    serde_json::Number::from_f64(value).unwrap_or_else(|| serde_json::Number::from(0)),
                ),
            );
            idx += 1;
        }
    }

    if let Some(msg_b64) = msg {
        if let Ok(msg_raw) = base64::engine::general_purpose::URL_SAFE_NO_PAD.decode(msg_b64.as_bytes()) {
            if let Ok(msg_str) = String::from_utf8(msg_raw) {
                out.insert("msg".to_string(), serde_json::Value::String(msg_str));
            }
        }
    }
    serde_json::Value::Object(out)
}

fn base64_urlsafe_no_pad(src: &[u8]) -> String {
    const TBL: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut out = String::with_capacity((src.len() * 4 + 2) / 3);
    let mut i = 0usize;
    while i + 3 <= src.len() {
        let n = ((src[i] as u32) << 16) | ((src[i + 1] as u32) << 8) | (src[i + 2] as u32);
        out.push(TBL[((n >> 18) & 63) as usize] as char);
        out.push(TBL[((n >> 12) & 63) as usize] as char);
        out.push(TBL[((n >> 6) & 63) as usize] as char);
        out.push(TBL[(n & 63) as usize] as char);
        i += 3;
    }
    let rem = src.len() - i;
    if rem == 1 {
        let n = (src[i] as u32) << 16;
        out.push(TBL[((n >> 18) & 63) as usize] as char);
        out.push(TBL[((n >> 12) & 63) as usize] as char);
    } else if rem == 2 {
        let n = ((src[i] as u32) << 16) | ((src[i + 1] as u32) << 8);
        out.push(TBL[((n >> 18) & 63) as usize] as char);
        out.push(TBL[((n >> 12) & 63) as usize] as char);
        out.push(TBL[((n >> 6) & 63) as usize] as char);
    }
    out
}

// ─────────────────────────────────────────────────────────────────────────────
// Per-call bump arena for auto_decompose_input_inner's temporary structures.
// ─────────────────────────────────────────────────────────────────────────────

thread_local! {
    static DECOMP_BUMP: RefCell<Bump> = RefCell::new(Bump::with_capacity(512));
}

// ─────────────────────────────────────────────────────────────────────────────
// Zero-alloc helper functions for compress_fact_inner hot path
// ─────────────────────────────────────────────────────────────────────────────

/// Borrow a UTF-8 string directly from the binary input slice (no heap copy).
fn read_str_ref<'a>(src: &'a [u8], off: &mut usize) -> Option<&'a str> {
    let len = read_u32_be(src, off)? as usize;
    let bytes = src.get(*off..(*off + len))?;
    *off += len;
    std::str::from_utf8(bytes).ok()
}

/// Write Base62-encoded i64 directly into `dst` without heap allocation.
fn push_b62_i64(dst: &mut String, value: i64) {
    if value == 0 {
        dst.push('0');
        return;
    }
    let neg = value < 0;
    let mut n: u64 = if neg { value.unsigned_abs() } else { value as u64 };
    let mut tmp = [0u8; 22];
    let mut idx = 0usize;
    while n > 0 && idx < tmp.len() - 1 {
        tmp[idx] = B62[(n % 62) as usize];
        n /= 62;
        idx += 1;
    }
    if neg { dst.push('-'); }
    while idx > 0 {
        idx -= 1;
        dst.push(tmp[idx] as char);
    }
}

/// Write Base62-encoded float directly into `dst` without heap allocation.
#[inline]
fn push_b62_num(dst: &mut String, n: f64, precision_val: i64, use_precision: bool) {
    let normalized = if use_precision {
        py_round_ties_even_to_i64(n * precision_val as f64)
    } else if n >= 0.0 {
        n.trunc() as i64
    } else {
        n.ceil() as i64
    };
    push_b62_i64(dst, normalized);
}

/// Write symbol-map lookup result into `dst`.
/// Uses a 64-byte stack buffer for the lowercase key to avoid allocation
/// for keys ≤ 64 bytes (covers virtually all real-world symbol names).
fn push_symbol(dst: &mut String, map: &HashMap<String, String>, key: &str) {
    let kb = key.as_bytes();
    if kb.len() <= 64 {
        let mut buf = [0u8; 64];
        for (i, &b) in kb.iter().enumerate() {
            buf[i] = b.to_ascii_lowercase();
        }
        // SAFETY: to_ascii_lowercase always produces valid ASCII ⊆ UTF-8
        let k = unsafe { std::str::from_utf8_unchecked(&buf[..kb.len()]) };
        if let Some(sym) = map.get(k) {
            dst.push_str(sym);
            return;
        }
    } else {
        let k = key.to_ascii_lowercase();
        if let Some(sym) = map.get(&k) {
            dst.push_str(sym);
            return;
        }
    }
    dst.push_str(key);
}

/// Write URL-safe no-pad base64 directly into `dst` without allocating
/// a temporary String (inline version of `base64_urlsafe_no_pad`).
fn push_base64_urlsafe_no_pad(dst: &mut String, src: &[u8]) {
    const TBL: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut i = 0usize;
    while i + 3 <= src.len() {
        let n = ((src[i] as u32) << 16) | ((src[i + 1] as u32) << 8) | (src[i + 2] as u32);
        dst.push(TBL[((n >> 18) & 63) as usize] as char);
        dst.push(TBL[((n >> 12) & 63) as usize] as char);
        dst.push(TBL[((n >> 6) & 63) as usize] as char);
        dst.push(TBL[(n & 63) as usize] as char);
        i += 3;
    }
    let rem = src.len() - i;
    if rem == 1 {
        let n = (src[i] as u32) << 16;
        dst.push(TBL[((n >> 18) & 63) as usize] as char);
        dst.push(TBL[((n >> 12) & 63) as usize] as char);
    } else if rem == 2 {
        let n = ((src[i] as u32) << 16) | ((src[i + 1] as u32) << 8);
        dst.push(TBL[((n >> 18) & 63) as usize] as char);
        dst.push(TBL[((n >> 12) & 63) as usize] as char);
        dst.push(TBL[((n >> 6) & 63) as usize] as char);
    }
}

/// Write a compressed unit directly into `dst` — zero-alloc inline version of
/// `compress_unit` that produces identical output.
fn push_compressed_unit(state: &CompressorState, unit_str: &str, dst: &mut String) {
    if unit_str.is_empty() || unit_str == "unknown" {
        dst.push('Z');
        return;
    }
    let mut first = true;
    for p in unit_str.split('/') {
        if !first { dst.push('/'); }
        first = false;
        let s = p.trim();
        if s.is_empty() { continue; }
        let bytes = s.as_bytes();
        // Locate trailing decimal-digit run (power suffix, e.g. "m2" → pwr="2")
        let mut i = bytes.len();
        while i > 0 && bytes[i - 1].is_ascii_digit() { i -= 1; }
        let pwr = &s[i..];
        let core = &s[..i];
        // Find where a leading numeric coefficient ends
        let mut last_ok = 0usize;
        for j in 1..=core.len() {
            if core.is_char_boundary(j) && core[..j].parse::<f64>().is_ok() {
                last_ok = j;
            }
        }
        if last_ok > 0 && last_ok < core.len() {
            // coefficient + attribute (e.g. "1000m")
            let attr = &core[last_ok..];
            let Ok(mut c_val) = core[..last_ok].parse::<f64>() else {
                push_symbol(dst, &state.units_map, core);
                dst.push_str(pwr);
                continue;
            };
            // Macro-prefix substitution (G/M/k/da).  Build "prefix+attr" in a
            // 68-byte stack buffer to avoid heap allocation.
            let mut combined = [0u8; 68];
            let attr_b = attr.as_bytes();
            let base_len = attr_b.len().min(combined.len());
            combined[..base_len].copy_from_slice(&attr_b[..base_len]);
            let mut combined_len = base_len;
            for (ms, factor) in [
                ("G", 1_000_000_000.0f64),
                ("M", 1_000_000.0),
                ("k", 1_000.0),
                ("da", 10.0),
            ] {
                if c_val >= factor {
                    let div = c_val / factor;
                    if (div - div.round()).abs() <= 1e-12 {
                        c_val = div;
                        let mp = ms.as_bytes();
                        let new_len = (mp.len() + attr_b.len()).min(combined.len());
                        // Shift attr bytes right to make room for prefix
                        combined.copy_within(0..attr_b.len().min(new_len - mp.len()), mp.len());
                        combined[..mp.len()].copy_from_slice(mp);
                        combined_len = new_len;
                        break;
                    }
                }
            }
            // SAFETY: combined is built from ASCII-only bytes
            let final_key = unsafe { std::str::from_utf8_unchecked(&combined[..combined_len]) };
            let is_direct = (c_val - c_val.trunc()).abs() <= 1e-12 && c_val.abs() >= 1.0;
            push_b62_num(dst, c_val, state.precision_val, !is_direct);
            dst.push(',');
            push_symbol(dst, &state.units_map, final_key);
            dst.push_str(pwr);
        } else if last_ok == core.len() && !core.is_empty() {
            // Pure number (no attribute)
            let Ok(c_val) = core.parse::<f64>() else {
                push_symbol(dst, &state.units_map, s);
                continue;
            };
            let is_direct = (c_val - c_val.trunc()).abs() <= 1e-12 && c_val.abs() >= 1.0;
            push_b62_num(dst, c_val, state.precision_val, !is_direct);
            dst.push_str(pwr);
        } else {
            // Pure attribute (no coefficient)
            push_symbol(dst, &state.units_map, core);
            dst.push_str(pwr);
        }
    }
}

#[derive(Debug)]
struct CompressorState {
    precision_val: i64,
    use_ms: bool,
    units_map: HashMap<String, String>,
    states_map: HashMap<String, String>,
}

#[derive(Debug, Default, Clone)]
struct AidFusionState {
    next_tid: u32,
    sig_to_tid: HashMap<Vec<u8>, u32>,
    tid_to_sig: HashMap<u32, Vec<u8>>,
    runtime_vals: HashMap<u32, Vec<Vec<u8>>>,
}

#[derive(Debug, Default)]
struct FusionState {
    aids: HashMap<u32, AidFusionState>,
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct RegistryTemplateDisk {
    sig: String,
    #[serde(default)]
    last_vals_bin: Vec<String>,
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct RegistryDisk {
    #[serde(default)]
    aid: String,
    #[serde(default)]
    templates: HashMap<String, RegistryTemplateDisk>,
}

fn registry_path_for_aid(registry_root: &str, aid: u32) -> PathBuf {
    let aid_str = format!("{:010}", aid);
    Path::new(registry_root)
        .join(&aid_str[0..2])
        .join(&aid_str[2..4])
        .join(format!("{}.json", aid))
}

fn load_aid_registry_into_state(state: &mut FusionState, aid: u32, registry_root: Option<&str>) {
    if state.aids.contains_key(&aid) {
        return;
    }
    let root = match registry_root {
        Some(v) if !v.is_empty() => v,
        _ => return,
    };
    let p = registry_path_for_aid(root, aid);
    let raw = match fs::read(&p) {
        Ok(v) => v,
        Err(_) => return,
    };
    let disk: RegistryDisk = match serde_json::from_slice(&raw) {
        Ok(v) => v,
        Err(_) => return,
    };

    let mut aid_state = AidFusionState {
        next_tid: 24,
        ..AidFusionState::default()
    };
    for (tid_str, tpl) in disk.templates {
        let tid = match tid_str.parse::<u32>() {
            Ok(v) => v,
            Err(_) => continue,
        };
        let sig_bytes = tpl.sig.into_bytes();
        aid_state.sig_to_tid.insert(sig_bytes.clone(), tid);
        aid_state.tid_to_sig.insert(tid, sig_bytes);
        let mut vals = Vec::new();
        for item in tpl.last_vals_bin {
            if let Ok(v) = base64::engine::general_purpose::STANDARD.decode(item.as_bytes()) {
                vals.push(v);
            }
        }
        if !vals.is_empty() {
            aid_state.runtime_vals.insert(tid, vals);
        }
        aid_state.next_tid = aid_state.next_tid.max(tid.saturating_add(1));
    }

    if !aid_state.tid_to_sig.is_empty() || !aid_state.runtime_vals.is_empty() {
        state.aids.insert(aid, aid_state);
    }
}

fn dump_aid_registry_from_state(state: &FusionState, aid: u32, registry_root: Option<&str>) {
    let root = match registry_root {
        Some(v) if !v.is_empty() => v,
        _ => return,
    };
    let aid_state = match state.aids.get(&aid) {
        Some(v) => v,
        None => return,
    };

    let mut templates: HashMap<String, RegistryTemplateDisk> = HashMap::new();
    for (tid, sig) in &aid_state.tid_to_sig {
        let vals = aid_state.runtime_vals.get(tid).cloned().unwrap_or_default();
        let encoded_vals: Vec<String> = vals
            .iter()
            .map(|v| base64::engine::general_purpose::STANDARD.encode(v))
            .collect();
        let sig_str = String::from_utf8(sig.clone()).unwrap_or_default();
        templates.insert(
            tid.to_string(),
            RegistryTemplateDisk {
                sig: sig_str,
                last_vals_bin: encoded_vals,
            },
        );
    }

    let disk = RegistryDisk {
        aid: aid.to_string(),
        templates,
    };
    let body = match serde_json::to_vec_pretty(&disk) {
        Ok(v) => v,
        Err(_) => return,
    };
    let p = registry_path_for_aid(root, aid);
    if let Some(parent) = p.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let _ = fs::write(p, body);
}

const JSON_FUSION_TTL_SECS: u64 = 3600;
const JSON_FUSION_MAX_CTX: usize = 2048;

type JsonFusionEntry = (Arc<Mutex<FusionState>>, u64);

fn unix_now_secs() -> u64 {
    match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(d) => d.as_secs(),
        Err(_) => 0,
    }
}

fn fusion_registry() -> &'static Mutex<HashMap<u64, Arc<Mutex<FusionState>>>> {
    static REG: OnceLock<Mutex<HashMap<u64, Arc<Mutex<FusionState>>>>> = OnceLock::new();
    REG.get_or_init(|| Mutex::new(HashMap::new()))
}

fn next_fusion_id() -> u64 {
    static NEXT: AtomicU64 = AtomicU64::new(1_000_000);
    NEXT.fetch_add(1, Ordering::Relaxed)
}

fn compressor_registry() -> &'static Mutex<HashMap<u64, Arc<CompressorState>>> {
    static REG: OnceLock<Mutex<HashMap<u64, Arc<CompressorState>>>> = OnceLock::new();
    REG.get_or_init(|| Mutex::new(HashMap::new()))
}

fn next_compressor_id() -> u64 {
    static NEXT: AtomicU64 = AtomicU64::new(1);
    NEXT.fetch_add(1, Ordering::Relaxed)
}

fn get_symbol(map: &HashMap<String, String>, key: &str) -> String {
    let k = key.to_ascii_lowercase();
    map.get(&k).cloned().unwrap_or_else(|| key.to_string())
}

fn split_coeff_attr_power(p: &str) -> (Option<String>, String, String) {
    let s = p.trim();
    if s.is_empty() {
        return (None, String::new(), String::new());
    }
    let bytes = s.as_bytes();
    let mut i = bytes.len();
    while i > 0 && bytes[i - 1].is_ascii_digit() {
        i -= 1;
    }
    let pwr = if i < bytes.len() { &s[i..] } else { "" };
    let core = &s[..i];
    let mut coeff: Option<String> = None;
    let mut attr = core.to_string();
    let mut last_ok = 0usize;
    for j in 1..=core.len() {
        if core[..j].parse::<f64>().is_ok() {
            last_ok = j;
        }
    }
    if last_ok > 0 && last_ok < core.len() {
        coeff = Some(core[..last_ok].to_string());
        attr = core[last_ok..].to_string();
    } else if last_ok == core.len() {
        coeff = Some(core.to_string());
        attr.clear();
    }
    (coeff, attr, pwr.to_string())
}

fn compress_unit(state: &CompressorState, unit_str: &str) -> String {
    if unit_str.is_empty() || unit_str == "unknown" {
        return "Z".to_string();
    }
    let mut compressed: Vec<String> = Vec::new();
    for p in unit_str.split('/') {
        let (coeff, attr, pwr) = split_coeff_attr_power(p);
        let p_suffix = pwr;
        if let Some(coeff_str) = coeff {
            let c_val_parse = coeff_str.parse::<f64>();
            if c_val_parse.is_err() {
                compressed.push(format!("{}{}", get_symbol(&state.units_map, &attr), p_suffix));
                continue;
            }
            let mut c_val = c_val_parse.unwrap_or(0.0);
            let mut final_attr = attr.clone();
            for (macro_sym, factor) in [("G", 1_000_000_000.0), ("M", 1_000_000.0), ("k", 1_000.0), ("da", 10.0)] {
                if c_val >= factor {
                    let div = c_val / factor;
                    if (div - div.round()).abs() <= 1e-12 {
                        c_val = div;
                        final_attr = format!("{}{}", macro_sym, attr);
                        break;
                    }
                }
            }
            let sym = get_symbol(&state.units_map, &final_attr);
            let is_direct = (c_val - c_val.trunc()).abs() <= 1e-12 && c_val.abs() >= 1.0;
            let c_enc = encode_b62_num(c_val, state.precision_val, !is_direct);
            compressed.push(format!("{},{}{}", c_enc, sym, p_suffix));
        } else {
            compressed.push(format!("{}{}", get_symbol(&state.units_map, &attr), p_suffix));
        }
    }
    compressed.join("/")
}

fn compress_fact_inner(state: &CompressorState, input: &[u8]) -> Option<Vec<u8>> {
    let mut off = 0usize;
    // read_str_ref: borrowed from `input`, zero allocation
    let device_id    = read_str_ref(input, &mut off)?;
    let dev_state    = read_str_ref(input, &mut off)?;
    let t_in         = read_f64_be(input, &mut off)?;
    let sensor_count = read_u32_be(input, &mut off)? as usize;

    let t_raw = if state.use_ms && t_in < 100_000_000_000.0 {
        (t_in * 1000.0).trunc() as u64
    } else {
        t_in.trunc() as u64
    };
    let t_bytes = t_raw.to_be_bytes();

    // Single heap allocation for the entire body string
    let mut body = String::with_capacity(256 + sensor_count * 28);
    body.push_str(device_id);
    body.push('.');
    push_symbol(&mut body, &state.states_map, dev_state);
    body.push('.');
    push_base64_urlsafe_no_pad(&mut body, &t_bytes[2..]);  // 6-byte ts → 8 chars, no alloc
    body.push('|');

    // Single-pass sensor loop: no intermediate Vec<(String,String,f64,String)>
    for _ in 0..sensor_count {
        let sid  = read_str_ref(input, &mut off)?;
        let sst  = read_str_ref(input, &mut off)?;
        let val  = read_f64_be(input, &mut off)?;
        let unit = read_str_ref(input, &mut off)?;
        body.push_str(sid);
        body.push('>');
        push_symbol(&mut body, &state.states_map, sst);
        body.push('.');
        push_compressed_unit(state, unit, &mut body);
        body.push(':');
        push_b62_num(&mut body, val, state.precision_val, true);
        body.push('|');
    }

    let geohash = read_opt_string(input, &mut off)?;
    let url     = read_opt_string(input, &mut off)?;
    let msg     = read_opt_string(input, &mut off)?;
    if off != input.len() {
        return None;
    }

    if let Some(geo) = geohash {
        body.push('&');
        body.push_str(&geo);
        body.push('|');
    }
    if let Some(url_val) = url {
        let trimmed = url_val.strip_prefix("https://").unwrap_or(url_val.as_str());
        body.push('#');
        push_base64_urlsafe_no_pad(&mut body, trimmed.as_bytes());
        body.push('|');
    }
    if let Some(msg_val) = msg {
        body.push('@');
        push_base64_urlsafe_no_pad(&mut body, msg_val.as_bytes());
    }

    Some(body.into_bytes())
}

fn read_blob(src: &[u8], off: &mut usize) -> Option<Vec<u8>> {
    let len = read_u32_be(src, off)? as usize;
    let bytes = src.get(*off..(*off + len))?;
    *off += len;
    Some(bytes.to_vec())
}

fn pack_fusion_result(cmd: u8, tid: u32, flags: u8, body: &[u8]) -> Option<Vec<u8>> {
    let mut out = Vec::with_capacity(10 + body.len());
    out.push(cmd);
    out.extend_from_slice(&tid.to_be_bytes());
    out.push(flags);
    push_u32_be(&mut out, body.len())?;
    out.extend_from_slice(body);
    Some(out)
}

fn get_or_init_aid_state<'a>(state: &'a mut FusionState, src_aid: u32) -> &'a mut AidFusionState {
    state.aids.entry(src_aid).or_insert_with(|| AidFusionState {
        next_tid: 24,
        ..AidFusionState::default()
    })
}

/// ③ Write u32 as decimal ASCII into a 10-byte stack buffer; return the filled slice.
#[inline]
fn u32_to_decimal_slice(n: u32, buf: &mut [u8; 10]) -> &[u8] {
    if n == 0 {
        buf[0] = b'0';
        return &buf[..1];
    }
    let mut i = 10usize;
    let mut x = n;
    while x > 0 {
        i -= 1;
        buf[i] = b'0' + (x % 10) as u8;
        x /= 10;
    }
    &buf[i..]
}

fn apply_fusion_state<V: AsRef<[u8]>>(
    state: &mut FusionState,
    src_aid: u32,
    strategy_full: bool,
    sig: &[u8],
    vals_bin: &[V],
) -> Option<Vec<u8>> {
    let aid_state = get_or_init_aid_state(state, src_aid);
    let mut new_template = false;
    // HashMap<Vec<u8>>::get accepts &[u8] via Borrow – no allocation in DIFF path
    let tid = match aid_state.sig_to_tid.get(sig).copied() {
        Some(v) => v,
        None => {
            let tid = aid_state.next_tid;
            aid_state.next_tid = aid_state.next_tid.saturating_add(1);
            let sig_owned = sig.to_vec();
            aid_state.sig_to_tid.insert(sig_owned.clone(), tid);
            aid_state.tid_to_sig.insert(tid, sig_owned);
            new_template = true;
            tid
        }
    };
    let tid_vals = aid_state.runtime_vals.entry(tid).or_default();
    let mut runtime_changed = false;

    if strategy_full {
        let same = tid_vals.len() == vals_bin.len()
            && tid_vals.iter().zip(vals_bin.iter()).all(|(s, v)| s.as_slice() == v.as_ref());
        if !same {
            *tid_vals = vals_bin.iter().map(|v| v.as_ref().to_vec()).collect();
            runtime_changed = true;
        }
        let mut flags = 0u8;
        if new_template { flags |= 0x01; }
        if runtime_changed { flags |= 0x02; }
        flags |= 0x04; // use raw_input body
        return pack_fusion_result(DATA_FULL, tid, flags, &[]);
    }

    if tid_vals.len() != vals_bin.len() {
        *tid_vals = vals_bin.iter().map(|v| v.as_ref().to_vec()).collect();
        runtime_changed = true;
        let mut flags = 0u8;
        if new_template { flags |= 0x01; }
        if runtime_changed { flags |= 0x02; }
        flags |= 0x04; // use raw_input body
        return pack_fusion_result(DATA_FULL, tid, flags, &[]);
    }

    let mut mask: u128 = 0;
    // ⑤ SmallVec: most diffs are tiny (1-2 changed sensors × ~10 bytes each)
    let mut diff_body: SmallVec<[u8; 64]> = SmallVec::new();
    let mut changed = false;
    for (i, v) in vals_bin.iter().enumerate() {
        let v_bytes = v.as_ref();
        if tid_vals.get(i).map(|s| s.as_slice()) != Some(v_bytes) {
            if i >= 128 {
                return None;
            }
            mask |= 1u128 << i;
            let v_len = u8::try_from(v_bytes.len()).ok()?;
            diff_body.push(v_len);
            diff_body.extend_from_slice(v_bytes);
            tid_vals[i] = v_bytes.to_vec();
            changed = true;
        }
    }
    if !changed {
        let mut flags = 0u8;
        if new_template { flags |= 0x01; }
        return pack_fusion_result(DATA_HEART, tid, flags, &[]);
    }
    runtime_changed = true;
    let mask_len = (vals_bin.len() + 7) / 8;
    let mask_bytes_full = mask.to_be_bytes();
    let mask_start = mask_bytes_full.len().saturating_sub(mask_len);
    // ⑤ SmallVec: mask (≤16 bytes) + diff_body together rarely exceed 80 bytes
    let mut body: SmallVec<[u8; 96]> = SmallVec::new();
    body.extend_from_slice(&mask_bytes_full[mask_start..]);
    body.extend_from_slice(&diff_body);
    let mut flags = 0u8;
    if new_template { flags |= 0x01; }
    if runtime_changed { flags |= 0x02; }
    pack_fusion_result(DATA_DIFF, tid, flags, &body)
}

fn replace_first_bytes(haystack: &mut Vec<u8>, needle: &[u8], replacement: &[u8]) -> bool {
    if needle.is_empty() {
        return false;
    }
    if let Some(pos) = haystack.windows(needle.len()).position(|w| w == needle) {
        haystack.splice(pos..pos + needle.len(), replacement.iter().copied());
        return true;
    }
    false
}

fn reconstruct_payload(sig: &[u8], ts_enc: &[u8], vals: &[Vec<u8>]) -> Option<Vec<u8>> {
    let mut out = sig.to_vec();
    if !replace_first_bytes(&mut out, b"{TS}", ts_enc) {
        return None;
    }
    for v in vals {
        if !replace_first_bytes(&mut out, &[1u8], v) {
            return None;
        }
    }
    Some(out)
}

fn apply_fusion_receive_state(
    state: &mut FusionState,
    src_aid: u32,
    base_cmd: u8,
    tid: u32,
    ts_enc: Vec<u8>,
    body: Vec<u8>,
) -> Option<Vec<u8>> {
    let aid_state = state.aids.get_mut(&src_aid)?;
    let sig = aid_state.tid_to_sig.get(&tid)?.clone();
    let tid_vals = aid_state.runtime_vals.get_mut(&tid)?;
    match base_cmd {
        DATA_HEART => reconstruct_payload(&sig, &ts_enc, tid_vals),
        DATA_DIFF => {
            if tid_vals.len() > 128 {
                return None;
            }
            let mask_len = (tid_vals.len() + 7) / 8;
            if body.len() < mask_len {
                return None;
            }
            let mut mask: u128 = 0;
            for &b in &body[..mask_len] {
                mask = (mask << 8) | (b as u128);
            }
            let mut off = mask_len;
            for i in 0..tid_vals.len() {
                if ((mask >> i) & 1) == 1 {
                    let v_len = *body.get(off)? as usize;
                    off += 1;
                    let end = off.checked_add(v_len)?;
                    let new_val = body.get(off..end)?.to_vec();
                    tid_vals[i] = new_val;
                    off = end;
                }
            }
            reconstruct_payload(&sig, &ts_enc, tid_vals)
        }
        _ => None,
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Base62 alphabet (identical to C / Python implementations)
// ─────────────────────────────────────────────────────────────────────────────
const B62: &[u8; 62] = b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";

/// Encode a signed 64-bit integer into a Base62 ASCII string.
///
/// # Safety
/// `out` must point to a buffer of at least `out_len` bytes.
/// Returns 1 on success, 0 on failure (null pointer or buffer too small).
#[no_mangle]
pub unsafe extern "C" fn os_b62_encode_i64(
    value: i64,
    out: *mut c_char,
    out_len: usize,
) -> i32 {
    if out.is_null() || out_len < 2 {
        return 0;
    }
    let out_bytes = std::slice::from_raw_parts_mut(out as *mut u8, out_len);

    if value == 0 {
        out_bytes[0] = b'0';
        out_bytes[1] = 0;
        return 1;
    }

    let neg = value < 0;
    let mut n: u64 = if neg { (value as i64).unsigned_abs() } else { value as u64 };

    let mut tmp = [0u8; 96];
    let mut idx = 0usize;
    while n > 0 && idx < tmp.len() - 1 {
        tmp[idx] = B62[(n % 62) as usize];
        n /= 62;
        idx += 1;
    }

    let needed = idx + usize::from(neg) + 1;
    if needed > out_len {
        return 0;
    }

    let mut w = 0usize;
    if neg {
        out_bytes[w] = b'-';
        w += 1;
    }
    while idx > 0 {
        idx -= 1;
        out_bytes[w] = tmp[idx];
        w += 1;
    }
    out_bytes[w] = 0;
    1
}

/// Decode a Base62 ASCII string to a signed 64-bit integer.
///
/// # Safety
/// `s` must be a null-terminated ASCII string. `ok` may be null.
/// Sets `*ok = 1` on success, `*ok = 0` on failure.
#[no_mangle]
pub unsafe extern "C" fn os_b62_decode_i64(s: *const c_char, ok: *mut i32) -> i64 {
    if let Some(ok_ref) = ok.as_mut() {
        *ok_ref = 0;
    }
    if s.is_null() || *s == 0 {
        return 0;
    }

    let bytes = std::ffi::CStr::from_ptr(s).to_bytes();
    let (neg, digits) = match bytes.first() {
        Some(&b'-') => (true, &bytes[1..]),
        _ => (false, bytes),
    };
    if digits.is_empty() {
        return 0;
    }

    let mut val: u64 = 0;
    for &b in digits {
        let d: u64 = if b.is_ascii_digit() {
            (b - b'0') as u64
        } else if b.is_ascii_lowercase() {
            10 + (b - b'a') as u64
        } else if b.is_ascii_uppercase() {
            36 + (b - b'A') as u64
        } else {
            return 0;
        };
        val = val.wrapping_mul(62).wrapping_add(d);
    }

    if let Some(ok_ref) = ok.as_mut() {
        *ok_ref = 1;
    }
    if neg { -(val as i64) } else { val as i64 }
}

// ─────────────────────────────────────────────────────────────────────────────
// CMD byte constants – must stay aligned with pycore/handshake.py CMD class
// ─────────────────────────────────────────────────────────────────────────────
const DATA_FULL: u8 = 63;
const DATA_FULL_SEC: u8 = 64;
const DATA_DIFF: u8 = 170;
const DATA_DIFF_SEC: u8 = 171;
const DATA_HEART: u8 = 127;
const DATA_HEART_SEC: u8 = 128;

const CRC16_POLY: u16 = 0x1021;
const CRC16_INIT: u16 = 0xFFFF;

// ─── CRC helpers (internal) ───────────────────────────────────────────────
fn crc8_inner(data: &[u8], poly: u8, init: u8) -> u8 {
    let mut crc = init;
    for &b in data {
        crc ^= b;
        for _ in 0..8 {
            if (crc & 0x80) != 0 {
                crc = (crc << 1) ^ poly;
            } else {
                crc <<= 1;
            }
        }
    }
    crc
}

fn crc16_ccitt(data: &[u8], poly: u16, init: u16) -> u16 {
    let mut crc = init;
    for &b in data {
        crc ^= (b as u16) << 8;
        for _ in 0..8 {
            if (crc & 0x8000) != 0 {
                crc = (crc << 1) ^ poly;
            } else {
                crc <<= 1;
            }
        }
    }
    crc
}

// ─── Public CRC exports (mirror C `os_security` ABI) ─────────────────────

/// Compute CRC-8 over `data[0..len]`.
///
/// Signature matches `os_security: os_crc8(data, len, poly, init) -> uint8`.
/// Default usage: `poly=7`, `init=0`.
///
/// # Safety
/// `data` must point to `len` readable bytes (or be null when `len == 0`).
#[no_mangle]
pub unsafe extern "C" fn os_crc8(
    data: *const u8,
    len: usize,
    poly: u16,  // uint16_t in C; only low 8 bits used
    init: u8,
) -> u8 {
    if data.is_null() || len == 0 {
        return init;
    }
    let slice = std::slice::from_raw_parts(data, len);
    crc8_inner(slice, poly as u8, init)
}

/// Compute CRC-16/CCITT over `data[0..len]`.
///
/// Signature matches `os_security: os_crc16_ccitt(data, len, poly, init) -> uint16`.
/// Default usage: `poly=0x1021`, `init=0xFFFF`.
///
/// # Safety
/// `data` must point to `len` readable bytes (or be null when `len == 0`).
#[no_mangle]
pub unsafe extern "C" fn os_crc16_ccitt(
    data: *const u8,
    len: usize,
    poly: u16,
    init: u16,
) -> u16 {
    if data.is_null() || len == 0 {
        return init;
    }
    let slice = std::slice::from_raw_parts(data, len);
    crc16_ccitt(slice, poly, init)
}

/// Backward-compatible alias used by the Rust codec helpers.
///
/// # Safety
/// `data` must point to `len` readable bytes (or be null when `len == 0`).
#[no_mangle]
pub unsafe extern "C" fn os_crc16_ccitt_pub(
    data: *const u8,
    len: usize,
    poly: u16,
    init: u16,
) -> u16 {
    os_crc16_ccitt(data, len, poly, init)
}

/// XOR payload bytes with the session key stream.
///
/// Signature matches `os_security: os_xor_payload(payload, payload_len, key, key_len, offset, out)`.
///
/// # Safety
/// `payload`, `key`, and `out` must point to readable/writable buffers of the
/// stated lengths when their lengths are non-zero.
#[no_mangle]
pub unsafe extern "C" fn os_xor_payload(
    payload: *const u8,
    payload_len: usize,
    key: *const u8,
    key_len: usize,
    offset: u32,
    out: *mut u8,
) {
    if out.is_null() {
        return;
    }
    if payload.is_null() || payload_len == 0 {
        return;
    }

    let payload_slice = std::slice::from_raw_parts(payload, payload_len);
    let out_slice = std::slice::from_raw_parts_mut(out, payload_len);
    let off = (offset & 31) as u8;

    if key.is_null() || key_len == 0 {
        out_slice.copy_from_slice(payload_slice);
        return;
    }

    let key_slice = std::slice::from_raw_parts(key, key_len);
    for (index, byte) in payload_slice.iter().enumerate() {
        out_slice[index] = byte ^ key_slice[(index + off as usize) % key_len] ^ off;
    }
}

/// Derive the 32-byte session key from `(assigned_id * timestamp_raw)`.
///
/// Signature matches `os_security: os_derive_session_key(assigned_id, timestamp_raw, out32)`.
///
/// # Safety
/// `out32` must point to at least 32 writable bytes.
#[no_mangle]
pub unsafe extern "C" fn os_derive_session_key(
    assigned_id: u64,
    timestamp_raw: u64,
    out32: *mut u8,
) {
    if out32.is_null() {
        return;
    }

    let seed = assigned_id.wrapping_mul(timestamp_raw);
    let digest = Sha256::digest(seed.to_string().as_bytes());
    std::ptr::copy_nonoverlapping(digest.as_ptr(), out32, digest.len());
}

/// Return 1 if `cmd` is a telemetry-data command (plain or secure), 0 otherwise.
#[no_mangle]
pub extern "C" fn os_cmd_is_data(cmd: u8) -> i32 {
    i32::from(matches!(
        cmd,
        DATA_FULL | DATA_FULL_SEC | DATA_DIFF | DATA_DIFF_SEC | DATA_HEART | DATA_HEART_SEC
    ))
}

/// Map a secure variant to its base data command; non-secure commands pass through.
#[no_mangle]
pub extern "C" fn os_cmd_normalize_data(cmd: u8) -> u8 {
    match cmd {
        DATA_FULL_SEC => DATA_FULL,
        DATA_DIFF_SEC => DATA_DIFF,
        DATA_HEART_SEC => DATA_HEART,
        other => other,
    }
}

/// Map a plain data command to its secure variant; non-data commands pass through.
#[no_mangle]
pub extern "C" fn os_cmd_secure_variant(cmd: u8) -> u8 {
    match cmd {
        DATA_FULL => DATA_FULL_SEC,
        DATA_DIFF => DATA_DIFF_SEC,
        DATA_HEART => DATA_HEART_SEC,
        other => other,
    }
}

/// Parse minimal packet header metadata.
///
/// Output layout (`out_u64`, len >= 9):
/// 0=cmd, 1=base_cmd, 2=secure(0|1), 3=route_count,
/// 4=tid_pos, 5=source_aid, 6=tid, 7=timestamp_raw, 8=crc16_ok(0|1)
///
/// Returns 1 on success, 0 on malformed input.
///
/// # Safety
/// `packet` must point to `packet_len` bytes, `out_u64` must have `out_len` slots.
#[no_mangle]
pub unsafe extern "C" fn os_parse_header_min(
    packet: *const u8,
    packet_len: usize,
    out_u64: *mut u64,
    out_len: usize,
) -> i32 {
    if packet.is_null() || out_u64.is_null() || out_len < 9 || packet_len < 5 {
        return 0;
    }
    let buf = std::slice::from_raw_parts(packet, packet_len);

    let cmd = buf[0];
    let route_count = buf[1] as usize;
    let tid_pos = 2usize + route_count.saturating_mul(4);
    if packet_len < tid_pos + 10 {
        return 0;
    }

    let base_cmd = os_cmd_normalize_data(cmd);
    let secure = if os_cmd_is_data(cmd) == 1 && base_cmd != cmd { 1u64 } else { 0u64 };

    let source_aid = if route_count > 0 {
        let s = &buf[tid_pos - 4..tid_pos];
        u32::from_be_bytes([s[0], s[1], s[2], s[3]]) as u64
    } else {
        0u64
    };

    let tid = buf[tid_pos] as u64;
    let ts = &buf[tid_pos + 1..tid_pos + 7];
    let mut ts8 = [0u8; 8];
    ts8[2..8].copy_from_slice(ts);
    let timestamp_raw = u64::from_be_bytes(ts8);

    let recv = u16::from_be_bytes([buf[packet_len - 2], buf[packet_len - 1]]);
    let calc = crc16_ccitt(&buf[..packet_len - 2], CRC16_POLY, CRC16_INIT);
    let crc16_ok = if recv == calc { 1u64 } else { 0u64 };

    let out = std::slice::from_raw_parts_mut(out_u64, out_len);
    out[0] = cmd as u64;
    out[1] = base_cmd as u64;
    out[2] = secure;
    out[3] = route_count as u64;
    out[4] = tid_pos as u64;
    out[5] = source_aid;
    out[6] = tid;
    out[7] = timestamp_raw;
    out[8] = crc16_ok;
    1
}

/// ④⑥ Core decompose: writes sig into caller-supplied `sig_buf` (cleared on entry).
/// raw_vals uses SmallVec<16> — fits ≤8 sensors without heap allocation.
/// Callers that process many items in a loop should reuse the same `sig_buf`.
fn auto_decompose_fill_sig<'a>(
    input: &'a str,
    sig_buf: &mut Vec<u8>,
) -> Option<(&'a str, SmallVec<[&'a [u8]; 16]>)> {
    let work = match input.split_once(';') {
        Some((_, tail)) => tail,
        None => input,
    };
    let (head, payload) = work.split_once('|')?;
    let (h_base, ts_str) = head.rsplit_once('.')?;

    // ④ SmallVec<16>: ≤8 sensors × 2 slices fits entirely on the stack
    let mut raw_vals: SmallVec<[&'a [u8]; 16]> = SmallVec::new();

    // ⑥ Write sig into the provided buffer (reset first); zero heap alloc per call
    //    when the buffer is reused across iterations.
    DECOMP_BUMP.with(|cell| {
        let mut bump = cell.borrow_mut();
        bump.reset();
        let mut s = bumpalo::collections::String::new_in(&*bump);
        s.push_str(h_base);
        s.push_str(".{TS}|");
        for seg in payload.split('|') {
            if seg.is_empty() {
                continue;
            }
            if let Some((tag, content)) = seg.split_once('>') {
                if let Some((meta, val)) = content.rsplit_once(':') {
                    raw_vals.push(meta.as_bytes());
                    raw_vals.push(val.as_bytes());
                    s.push_str(tag);
                    s.push_str(">\x01:\x01|");
                    continue;
                }
            }
            s.push_str(seg);
            s.push('|');
        }
        sig_buf.clear();
        sig_buf.extend_from_slice(s.as_bytes());
    });

    Some((ts_str, raw_vals))
}

/// Thin wrapper: allocates a fresh sig Vec per call (for single-item callers).
fn auto_decompose_input_inner<'a>(
    input: &'a str,
) -> Option<(&'a str, Vec<u8>, SmallVec<[&'a [u8]; 16]>)> {
    let mut sig_buf = Vec::new();
    let (ts, vals) = auto_decompose_fill_sig(input, &mut sig_buf)?;
    Some((ts, sig_buf, vals))
}

/// Decompose a compressed OpenSynaptic string payload into:
///   ts_str, full_sig(with \x01 placeholders), raw_vals[]
/// using a compact binary envelope suitable for ctypes transfer.
///
/// Output binary layout:
///   u32 ts_len | u32 sig_len | u32 val_count |
///   ts_bytes | sig_bytes | repeat(val_count){ u32 len | bytes }
///
/// Return value:
///   >0  = bytes written
///   <0  = required output size (caller should retry with -ret bytes)
///    0  = malformed input / UTF-8 decode error
///
/// # Safety
/// `input` must point to `input_len` readable bytes.
/// `out` may be null when caller only wants the required length.
#[no_mangle]
pub unsafe extern "C" fn os_auto_decompose_input(
    input: *const u8,
    input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    if input.is_null() || input_len == 0 {
        return 0;
    }
    let raw = std::slice::from_raw_parts(input, input_len);
    let text = match std::str::from_utf8(raw) {
        Ok(v) => v,
        Err(_) => return 0,
    };
    let (ts, full_sig, vals) = match auto_decompose_input_inner(text) {
        Some(v) => v,
        None => return 0,
    };

    let mut encoded = Vec::with_capacity(input_len.saturating_mul(2).saturating_add(64));
    if push_u32_be(&mut encoded, ts.len()).is_none()
        || push_u32_be(&mut encoded, full_sig.len()).is_none()
        || push_u32_be(&mut encoded, vals.len()).is_none()
    {
        return 0;
    }
    encoded.extend_from_slice(ts.as_bytes());
    encoded.extend_from_slice(&full_sig);
    for v in &vals {
        if push_u32_be(&mut encoded, v.len()).is_none() {
            return 0;
        }
        encoded.extend_from_slice(*v);
    }

    let needed = encoded.len();
    let needed_i32 = match i32::try_from(needed) {
        Ok(v) => v,
        Err(_) => return 0,
    };
    if out.is_null() || out_len < needed {
        return -needed_i32;
    }
    std::ptr::copy_nonoverlapping(encoded.as_ptr(), out, needed);
    needed_i32
}

/// Create a Rust compressor handle.
///
/// Spec blob layout:
///   u32 precision | u8 use_ms |
///   u32 units_count | repeat(units_count){ str key | str val } |
///   u32 states_count | repeat(states_count){ str key | str val }
///
/// Returns 0 on failure, otherwise a non-zero handle.
#[no_mangle]
pub unsafe extern "C" fn os_compressor_create_v1(spec: *const u8, spec_len: usize) -> u64 {
    if spec.is_null() || spec_len == 0 {
        return 0;
    }
    let raw = std::slice::from_raw_parts(spec, spec_len);
    let mut off = 0usize;
    let precision = match read_u32_be(raw, &mut off) {
        Some(v) => v,
        None => return 0,
    };
    let use_ms = match read_u8(raw, &mut off) {
        Some(v) => v != 0,
        None => return 0,
    };
    if precision > 18 {
        return 0;
    }
    let mut units_map = HashMap::new();
    let units_count = match read_u32_be(raw, &mut off) {
        Some(v) => v as usize,
        None => return 0,
    };
    for _ in 0..units_count {
        let k = match read_string(raw, &mut off) {
            Some(v) => v,
            None => return 0,
        };
        let v = match read_string(raw, &mut off) {
            Some(v) => v,
            None => return 0,
        };
        units_map.insert(k.to_ascii_lowercase(), v);
    }
    let mut states_map = HashMap::new();
    let states_count = match read_u32_be(raw, &mut off) {
        Some(v) => v as usize,
        None => return 0,
    };
    for _ in 0..states_count {
        let k = match read_string(raw, &mut off) {
            Some(v) => v,
            None => return 0,
        };
        let v = match read_string(raw, &mut off) {
            Some(v) => v,
            None => return 0,
        };
        states_map.insert(k.to_ascii_lowercase(), v);
    }
    if off != raw.len() {
        return 0;
    }
    let state = CompressorState {
        precision_val: 10i64.pow(precision),
        use_ms,
        units_map,
        states_map,
    };
    let handle = next_compressor_id();
    if let Ok(mut reg) = compressor_registry().lock() {
        reg.insert(handle, Arc::new(state));
        handle
    } else {
        0
    }
}

/// Release a compressor handle. Returns 1 on success, 0 when the handle is missing.
#[no_mangle]
pub extern "C" fn os_compressor_free_v1(handle: u64) -> i32 {
    if handle == 0 {
        return 0;
    }
    if let Ok(mut reg) = compressor_registry().lock() {
        i32::from(reg.remove(&handle).is_some())
    } else {
        0
    }
}

/// Compress a standardized fact into the exact pycore solidity string format.
///
/// Input blob layout:
///   str id | str state | f64 t | u32 sensor_count |
///   repeat(sensor_count){ str sensor_id | str sensor_state | f64 value | str unit } |
///   opt_str geohash | opt_str url | opt_str msg
///
/// Return value:
///   >0  = bytes written
///   <0  = required output size
///    0  = malformed input / invalid handle
#[no_mangle]
pub unsafe extern "C" fn os_compress_fact_v1(
    handle: u64,
    input: *const u8,
    input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    if handle == 0 || input.is_null() || input_len == 0 {
        return 0;
    }
    let state = {
        let reg = match compressor_registry().lock() {
            Ok(v) => v,
            Err(_) => return 0,
        };
        match reg.get(&handle) {
            Some(v) => Arc::clone(v),
            None => return 0,
        }
    };
    let raw = std::slice::from_raw_parts(input, input_len);
    let encoded = match compress_fact_inner(&state, raw) {
        Some(v) => v,
        None => return 0,
    };
    let needed = encoded.len();
    let needed_i32 = match i32::try_from(needed) {
        Ok(v) => v,
        Err(_) => return 0,
    };
    if out.is_null() || out_len < needed {
        return -needed_i32;
    }
    std::ptr::copy_nonoverlapping(encoded.as_ptr(), out, needed);
    needed_i32
}

/// Create a fusion state handle for outbound template/runtime caching.
#[no_mangle]
pub extern "C" fn os_fusion_state_create_v1() -> u64 {
    let handle = next_fusion_id();
    if let Ok(mut reg) = fusion_registry().lock() {
        reg.insert(handle, Arc::new(Mutex::new(FusionState::default())));
        handle
    } else {
        0
    }
}

/// Free a fusion state handle.
#[no_mangle]
pub extern "C" fn os_fusion_state_free_v1(handle: u64) -> i32 {
    if handle == 0 {
        return 0;
    }
    if let Ok(mut reg) = fusion_registry().lock() {
        i32::from(reg.remove(&handle).is_some())
    } else {
        0
    }
}

/// Seed/replace one AID cache from Python registry state.
///
/// Input layout:
///   u32 src_aid | u32 template_count |
///   repeat(template_count){
///       u32 tid | blob sig | u32 val_count | repeat(val_count){ blob value }
///   }
#[no_mangle]
pub unsafe extern "C" fn os_fusion_state_seed_v1(
    handle: u64,
    input: *const u8,
    input_len: usize,
) -> i32 {
    if handle == 0 || input.is_null() || input_len == 0 {
        return 0;
    }
    let arc = {
        let reg = match fusion_registry().lock() {
            Ok(v) => v,
            Err(_) => return 0,
        };
        match reg.get(&handle) {
            Some(v) => Arc::clone(v),
            None => return 0,
        }
    };
    let raw = std::slice::from_raw_parts(input, input_len);
    let mut off = 0usize;
    let src_aid = match read_u32_be(raw, &mut off) {
        Some(v) => v,
        None => return 0,
    };
    let template_count = match read_u32_be(raw, &mut off) {
        Some(v) => v as usize,
        None => return 0,
    };
    let mut aid_state = AidFusionState::default();
    let mut max_tid = 0u32;
    for _ in 0..template_count {
        let tid = match read_u32_be(raw, &mut off) {
            Some(v) => v,
            None => return 0,
        };
        let sig = match read_blob(raw, &mut off) {
            Some(v) => v,
            None => return 0,
        };
        let val_count = match read_u32_be(raw, &mut off) {
            Some(v) => v as usize,
            None => return 0,
        };
        let mut vals = Vec::with_capacity(val_count);
        for _ in 0..val_count {
            let v = match read_blob(raw, &mut off) {
                Some(v) => v,
                None => return 0,
            };
            vals.push(v);
        }
        aid_state.sig_to_tid.insert(sig.clone(), tid);
        aid_state.tid_to_sig.insert(tid, sig);
        aid_state.runtime_vals.insert(tid, vals);
        max_tid = max_tid.max(tid);
    }
    if off != raw.len() {
        return 0;
    }
    aid_state.next_tid = max_tid.saturating_add(1).max(1);
    let mut state = match arc.lock() {
        Ok(v) => v,
        Err(_) => return 0,
    };
    state.aids.insert(src_aid, aid_state);
    1
}

/// Apply outbound run_engine state logic for one packet.
///
/// Input layout:
///   u32 src_aid | u8 strategy_full | blob sig | u32 val_count | repeat(val_count){ blob value }
///
/// Output layout:
///   u8 cmd | u32 tid | u8 flags | u32 body_len | body
///
/// flags:
///   bit0 = new_template
///   bit1 = runtime_changed
///   bit2 = use_raw_input_body
#[no_mangle]
pub unsafe extern "C" fn os_fusion_state_apply_v1(
    handle: u64,
    input: *const u8,
    input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    if handle == 0 || input.is_null() || input_len == 0 {
        return 0;
    }
    let arc = {
        let reg = match fusion_registry().lock() {
            Ok(v) => v,
            Err(_) => return 0,
        };
        match reg.get(&handle) {
            Some(v) => Arc::clone(v),
            None => return 0,
        }
    };
    let raw = std::slice::from_raw_parts(input, input_len);
    let mut off = 0usize;
    let src_aid = match read_u32_be(raw, &mut off) {
        Some(v) => v,
        None => return 0,
    };
    let strategy_full = match read_u8(raw, &mut off) {
        Some(v) => v != 0,
        None => return 0,
    };
    let sig = match read_blob(raw, &mut off) {
        Some(v) => v,
        None => return 0,
    };
    let val_count = match read_u32_be(raw, &mut off) {
        Some(v) => v as usize,
        None => return 0,
    };
    let mut vals = Vec::with_capacity(val_count);
    for _ in 0..val_count {
        let v = match read_blob(raw, &mut off) {
            Some(v) => v,
            None => return 0,
        };
        vals.push(v);
    }
    if off != raw.len() {
        return 0;
    }
    let encoded = {
        let mut state = match arc.lock() {
            Ok(v) => v,
            Err(_) => return 0,
        };
        match apply_fusion_state(&mut state, src_aid, strategy_full, &sig, &vals) {
            Some(v) => v,
            None => return 0,
        }
    };
    let needed = encoded.len();
    let needed_i32 = match i32::try_from(needed) {
        Ok(v) => v,
        Err(_) => return 0,
    };
    if out.is_null() || out_len < needed {
        return -needed_i32;
    }
    std::ptr::copy_nonoverlapping(encoded.as_ptr(), out, needed);
    needed_i32
}

/// Reconstruct a FULL-resolved raw payload for inbound HEART/DIFF packets.
///
/// Input layout:
///   u32 src_aid | u8 base_cmd | u32 tid | blob ts_enc | blob body
///
/// Output:
///   raw UTF-8 payload bytes suitable for `OpenSynapticEngine.decompress()`
#[no_mangle]
pub unsafe extern "C" fn os_fusion_state_receive_apply_v1(
    handle: u64,
    input: *const u8,
    input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    if handle == 0 || input.is_null() || input_len == 0 {
        return 0;
    }
    let arc = {
        let reg = match fusion_registry().lock() {
            Ok(v) => v,
            Err(_) => return 0,
        };
        match reg.get(&handle) {
            Some(v) => Arc::clone(v),
            None => return 0,
        }
    };
    let raw = std::slice::from_raw_parts(input, input_len);
    let mut off = 0usize;
    let src_aid = match read_u32_be(raw, &mut off) {
        Some(v) => v,
        None => return 0,
    };
    let base_cmd = match read_u8(raw, &mut off) {
        Some(v) => v,
        None => return 0,
    };
    let tid = match read_u32_be(raw, &mut off) {
        Some(v) => v,
        None => return 0,
    };
    let ts_enc = match read_blob(raw, &mut off) {
        Some(v) => v,
        None => return 0,
    };
    let body = match read_blob(raw, &mut off) {
        Some(v) => v,
        None => return 0,
    };
    if off != raw.len() {
        return 0;
    }
    let resolved = {
        let mut state = match arc.lock() {
            Ok(v) => v,
            Err(_) => return 0,
        };
        match apply_fusion_receive_state(&mut state, src_aid, base_cmd, tid, ts_enc, body) {
            Some(v) => v,
            None => return 0,
        }
    };
    let needed = resolved.len();
    let needed_i32 = match i32::try_from(needed) {
        Ok(v) => v,
        Err(_) => return 0,
    };
    if out.is_null() || out_len < needed {
        return -needed_i32;
    }
    std::ptr::copy_nonoverlapping(resolved.as_ptr(), out, needed);
    needed_i32
}

// ─────────────────────────────────────────────────────────────────────────────
// Metadata
// ─────────────────────────────────────────────────────────────────────────────

/// Write a null-terminated version string into `out`.
///
/// # Safety
/// `out` must point to a buffer of at least `out_len` bytes.
#[no_mangle]
pub unsafe extern "C" fn os_rscore_version(out: *mut c_char, out_len: usize) -> i32 {
    const VER: &[u8] = b"opensynaptic_rscore/1.2.0\0";
    if out.is_null() || out_len < VER.len() {
        return 0;
    }
    let dst = std::slice::from_raw_parts_mut(out as *mut u8, out_len);
    dst[..VER.len()].copy_from_slice(VER);
    1
}

fn write_stub_json(out: *mut u8, out_len: usize, body: &[u8]) -> i32 {
    let needed_i32 = match i32::try_from(body.len()) {
        Ok(v) => v,
        Err(_) => return 0,
    };
    if out.is_null() || out_len < body.len() {
        return -needed_i32;
    }
    unsafe {
        std::ptr::copy_nonoverlapping(body.as_ptr(), out, body.len());
    }
    needed_i32
}

fn write_out_bytes(out: *mut u8, out_len: usize, body: &[u8]) -> i32 {
    let needed_i32 = match i32::try_from(body.len()) {
        Ok(v) => v,
        Err(_) => return 0,
    };
    if out.is_null() || out_len < body.len() {
        return -needed_i32;
    }
    unsafe {
        std::ptr::copy_nonoverlapping(body.as_ptr(), out, body.len());
    }
    needed_i32
}

fn json_fusion_registry() -> &'static Mutex<HashMap<u64, JsonFusionEntry>> {
    static REG: OnceLock<Mutex<HashMap<u64, JsonFusionEntry>>> = OnceLock::new();
    REG.get_or_init(|| Mutex::new(HashMap::new()))
}

fn get_json_fusion_arc(ctx_id: u64) -> Option<Arc<Mutex<FusionState>>> {
    let key = if ctx_id == 0 { 1 } else { ctx_id };
    let now = unix_now_secs();
    let mut reg = json_fusion_registry().lock().ok()?;
    reg.retain(|_, (_, ts)| now.saturating_sub(*ts) <= JSON_FUSION_TTL_SECS);
    if let Some((arc, ts)) = reg.get_mut(&key) {
        *ts = now;
        return Some(Arc::clone(arc));
    }
    if reg.len() >= JSON_FUSION_MAX_CTX {
        let mut oldest_key = None;
        let mut oldest_ts = u64::MAX;
        for (ctx_key, (_, ts)) in reg.iter() {
            if *ts < oldest_ts {
                oldest_ts = *ts;
                oldest_key = Some(*ctx_key);
            }
        }
        if let Some(drop_key) = oldest_key {
            reg.remove(&drop_key);
        }
    }
    let arc = Arc::new(Mutex::new(FusionState::default()));
    reg.insert(key, (Arc::clone(&arc), now));
    Some(arc)
}

#[derive(Debug, Deserialize)]
struct FusionRunReq {
    #[serde(default)]
    ctx_id: u64,
    raw_input: String,
    #[serde(default)]
    strategy: String,
    #[serde(default)]
    src_aid: Option<u32>,
    #[serde(default)]
    registry_root: Option<String>,
}

#[derive(Debug, Deserialize)]
struct FusionDecompressReq {
    #[serde(default)]
    ctx_id: u64,
    packet_b64: String,
    #[serde(default)]
    registry_root: Option<String>,
}

#[derive(Debug, Serialize)]
struct PacketMetaOut {
    cmd: u8,
    base_cmd: u8,
    secure: bool,
    source_aid: u32,
    tid: u32,
    timestamp_raw: u64,
    crc16_ok: bool,
}

fn parse_src_aid(raw_input: &str) -> u32 {
    if let Some((prefix, _)) = raw_input.split_once(';') {
        if let Ok(v) = prefix.trim().parse::<u32>() {
            return v;
        }
    }
    0
}

/// ① Zero-copy: returns a borrow of the body slice instead of to_vec().
fn parse_apply_blob(encoded: &[u8]) -> Option<(u8, u32, u8, &[u8])> {
    if encoded.len() < 10 {
        return None;
    }
    let cmd = encoded[0];
    let tid = u32::from_be_bytes([encoded[1], encoded[2], encoded[3], encoded[4]]);
    let flags = encoded[5];
    let body_len = u32::from_be_bytes([encoded[6], encoded[7], encoded[8], encoded[9]]) as usize;
    if encoded.len() < 10 + body_len {
        return None;
    }
    Some((cmd, tid, flags, &encoded[10..10 + body_len]))
}

/// JSON ABI export for fusion run path.
#[no_mangle]
pub unsafe extern "C" fn os_fusion_run_json_v1(
    input: *const u8,
    input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    if input.is_null() || input_len == 0 {
        return 0;
    }
    let raw = std::slice::from_raw_parts(input, input_len);
    let req: FusionRunReq = match serde_json::from_slice(raw) {
        Ok(v) => v,
        Err(_) => return write_stub_json(out, out_len, br#"{"error":"invalid_json"}"#),
    };

    let (ts, sig, vals) = match auto_decompose_input_inner(&req.raw_input) {
        Some(v) => v,
        None => return write_stub_json(out, out_len, br#"{"error":"auto_decompose_failed"}"#),
    };

    let src_aid = req.src_aid.unwrap_or_else(|| parse_src_aid(&req.raw_input));
    let strategy_full = req.strategy.eq_ignore_ascii_case("FULL") || req.strategy.eq_ignore_ascii_case("FULL_PACKET");
    let arc = match get_json_fusion_arc(req.ctx_id) {
        Some(v) => v,
        None => return 0,
    };
    let encoded = {
        let mut state = match arc.lock() {
            Ok(v) => v,
            Err(_) => return 0,
        };
        load_aid_registry_into_state(&mut state, src_aid, req.registry_root.as_deref());
        let out = match apply_fusion_state(&mut state, src_aid, strategy_full, &sig, &vals) {
            Some(v) => v,
            None => return 0,
        };
        if let Some((_, _, flags, _)) = parse_apply_blob(&out) {
            if (flags & 0x03) != 0 {
                dump_aid_registry_from_state(&state, src_aid, req.registry_root.as_deref());
            }
        }
        out
    };
    let (cmd, tid, flags, body_native) = match parse_apply_blob(&encoded) {
        Some(v) => v,
        None => return 0,
    };

    // ① body_native: &[u8] — no to_vec() in DIFF path
    // ts is &str borrowed from req.raw_input; finalize_packet accepts &str directly
    let packet = if (flags & 0x04) != 0 {
        let full_body = req.raw_input.as_bytes().to_vec();
        match finalize_packet(cmd, src_aid, tid, ts, &full_body) {
            Some(v) => v,
            None => return 0,
        }
    } else {
        match finalize_packet(cmd, src_aid, tid, ts, body_native) {
            Some(v) => v,
            None => return 0,
        }
    };
    write_out_bytes(out, out_len, &packet)
}

/// JSON ABI export for fusion decompress path.
#[no_mangle]
pub unsafe extern "C" fn os_fusion_decompress_json_v1(
    input: *const u8,
    input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    if input.is_null() || input_len == 0 {
        return 0;
    }
    let raw = std::slice::from_raw_parts(input, input_len);
    let req: FusionDecompressReq = match serde_json::from_slice(raw) {
        Ok(v) => v,
        Err(_) => return write_stub_json(out, out_len, br#"{"error":"invalid_json"}"#),
    };

    let packet = match base64::engine::general_purpose::STANDARD.decode(req.packet_b64.as_bytes()) {
        Ok(v) => v,
        Err(_) => return write_stub_json(out, out_len, br#"{"error":"invalid_packet_b64"}"#),
    };
    if packet.len() < 5 {
        return write_stub_json(out, out_len, br#"{"error":"Packet too short"}"#);
    }

    let cmd = packet[0];
    let route_count = packet[1] as usize;
    let tid_pos = 2usize + route_count.saturating_mul(4);
    if packet.len() < tid_pos + 10 {
        return write_stub_json(out, out_len, br#"{"error":"Incomplete Binary Header"}"#);
    }

    let base_cmd = os_cmd_normalize_data(cmd);
    let secure = os_cmd_is_data(cmd) == 1 && base_cmd != cmd;
    let source_aid = if route_count > 0 {
        let s = &packet[tid_pos - 4..tid_pos];
        u32::from_be_bytes([s[0], s[1], s[2], s[3]])
    } else {
        0
    };
    let tid = packet[tid_pos] as u32;
    let ts_raw = &packet[tid_pos + 1..tid_pos + 7];
    let mut ts8 = [0u8; 8];
    ts8[2..8].copy_from_slice(ts_raw);
    let timestamp_raw = u64::from_be_bytes(ts8);
    let recv_crc16 = u16::from_be_bytes([packet[packet.len() - 2], packet[packet.len() - 1]]);
    let calc_crc16 = crc16_ccitt(&packet[..packet.len() - 2], CRC16_POLY, CRC16_INIT);
    let crc16_ok = recv_crc16 == calc_crc16;

    if !crc16_ok {
        let mut out_map = serde_json::Map::new();
        out_map.insert("error".to_string(), serde_json::Value::String("CRC16 mismatch".to_string()));
        let meta = PacketMetaOut {
            cmd,
            base_cmd,
            secure,
            source_aid,
            tid,
            timestamp_raw,
            crc16_ok,
        };
        out_map.insert("__packet_meta__".to_string(), serde_json::to_value(meta).unwrap_or(serde_json::Value::Null));
        let out_json = serde_json::to_vec(&serde_json::Value::Object(out_map)).unwrap_or_else(|_| br#"{"error":"json_encode_failed"}"#.to_vec());
        return write_out_bytes(out, out_len, &out_json);
    }

    let body = packet[tid_pos + 7..packet.len() - 3].to_vec();
    let ts_enc = base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(ts_raw);
    let arc = match get_json_fusion_arc(req.ctx_id) {
        Some(v) => v,
        None => return 0,
    };

    let payload = if base_cmd == DATA_FULL {
        let p = String::from_utf8(body.clone()).unwrap_or_default();
        if let Some((_, sig, vals)) = auto_decompose_input_inner(&p) {
            if let Ok(mut state) = arc.lock() {
                load_aid_registry_into_state(&mut state, source_aid, req.registry_root.as_deref());
                let aid_state = get_or_init_aid_state(&mut state, source_aid);
                aid_state.sig_to_tid.insert(sig.clone(), tid);
                aid_state.tid_to_sig.insert(tid, sig);
                // Convert borrowed slices to owned Vec<u8> for persistent storage
                aid_state.runtime_vals.insert(tid, vals.into_iter().map(|s| s.to_vec()).collect());
                aid_state.next_tid = aid_state.next_tid.max(tid.saturating_add(1));
                dump_aid_registry_from_state(&state, source_aid, req.registry_root.as_deref());
            }
        }
        p
    } else if base_cmd == DATA_DIFF || base_cmd == DATA_HEART {
        let resolved = {
            let mut state = match arc.lock() {
                Ok(v) => v,
                Err(_) => return 0,
            };
            load_aid_registry_into_state(&mut state, source_aid, req.registry_root.as_deref());
            match apply_fusion_receive_state(&mut state, source_aid, base_cmd, tid, ts_enc.into_bytes(), body) {
                Some(v) => {
                    if base_cmd == DATA_DIFF {
                        dump_aid_registry_from_state(&state, source_aid, req.registry_root.as_deref());
                    }
                    v
                }
                None => return write_stub_json(out, out_len, br#"{"error":"fusion_receive_apply_failed"}"#),
            }
        };
        String::from_utf8(resolved).unwrap_or_default()
    } else {
        return write_stub_json(out, out_len, br#"{"error":"unknown_command"}"#);
    };

    let payload_no_aid = match payload.split_once(';') {
        Some((_, tail)) => tail,
        None => payload.as_str(),
    };
    let mut decoded = parse_compressed_payload_to_json(payload_no_aid, 10_000);
    if let serde_json::Value::Object(ref mut map) = decoded {
        let meta = PacketMetaOut {
            cmd,
            base_cmd,
            secure,
            source_aid,
            tid,
            timestamp_raw,
            crc16_ok,
        };
        map.insert("__packet_meta__".to_string(), serde_json::to_value(meta).unwrap_or(serde_json::Value::Null));
    }
    let out_json = serde_json::to_vec(&decoded).unwrap_or_else(|_| br#"{"error":"json_encode_failed"}"#.to_vec());
    write_out_bytes(out, out_len, &out_json)
}

/// JSON ABI export for fusion relay path.
#[no_mangle]
pub unsafe extern "C" fn os_fusion_relay_json_v1(
    input: *const u8,
    input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    os_fusion_run_json_v1(input, input_len, out, out_len)
}

/// Placeholder JSON ABI export for node ensure_id path.
#[no_mangle]
pub unsafe extern "C" fn os_node_ensure_id_json_v1(
    _input: *const u8,
    _input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    write_stub_json(out, out_len, br#"{"ok":false,"error":"os_node_ensure_id_json_v1_not_implemented"}"#)
}

/// Placeholder JSON ABI export for node transmit path.
#[no_mangle]
pub unsafe extern "C" fn os_node_transmit_json_v1(
    _input: *const u8,
    _input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    write_stub_json(out, out_len, br#"{"ok":false,"error":"os_node_transmit_json_v1_not_implemented"}"#)
}

/// Placeholder JSON ABI export for node dispatch path.
#[no_mangle]
pub unsafe extern "C" fn os_node_dispatch_json_v1(
    _input: *const u8,
    _input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    write_stub_json(out, out_len, br#"{"ok":false,"error":"os_node_dispatch_json_v1_not_implemented"}"#)
}

// ─────────────────────────────────────────────────────────────────────────────
// Batch pipeline ABI – single Rust call for N compress+fuse items
// ─────────────────────────────────────────────────────────────────────────────

/// Inner batch pipeline – returns None only on unrecoverable structural error.
///
/// Input layout (all multi-byte integers are big-endian unless noted):
///   u64  compressor_handle  (BE)
///   u64  ctx_id             (BE)
///   u32  item_count         (BE)
///   u32  registry_root_len  (BE)
///   bytes registry_root[registry_root_len]
///   repeat(item_count) {
///       u32  aid            (BE)
///       u8   strategy       (1 = FULL, 0 = DIFF)
///       u32  fact_len       (BE)
///       bytes fact[fact_len]
///   }
///
/// Output layout:
///   u32  item_count   (BE)
///   repeat(item_count) {
///       u32  packet_len  (BE, 0 when that item failed)
///       bytes packet[packet_len]
///   }

fn pipeline_batch_inner(raw: &[u8]) -> Option<Vec<u8>> {
    if raw.len() < 20 {
        return None;
    }
    let comp_handle = u64::from_be_bytes(raw[0..8].try_into().ok()?);
    let ctx_id = u64::from_be_bytes(raw[8..16].try_into().ok()?);
    let mut off = 16usize;
    let item_count = read_u32_be(raw, &mut off)? as usize;
    let registry_root_len = read_u32_be(raw, &mut off)? as usize;
    if off + registry_root_len > raw.len() {
        return None;
    }
    let registry_root = if registry_root_len > 0 {
        String::from_utf8(raw[off..off + registry_root_len].to_vec()).ok()
    } else {
        None
    };
    off += registry_root_len;

    // ── Acquire compressor once (one mutex round-trip for all items) ──────
    let compressor = {
        let reg = compressor_registry().lock().ok()?;
        Arc::clone(reg.get(&comp_handle)?)
    };

    // ── Acquire fusion state once and hold it for the entire batch ─────────
    let fusion_arc = get_json_fusion_arc(ctx_id)?;
    let mut fusion_state = fusion_arc.lock().ok()?;

    // ── Process items ──────────────────────────────────────────────────────
    let mut out: Vec<u8> = Vec::with_capacity(4 + item_count * 24);
    push_u32_be(&mut out, item_count)?;

    // ⑦ Allocate sig_buf once per batch; reused across all items — saves N-1 sig allocs per batch.
    let mut sig_buf: Vec<u8> = Vec::with_capacity(256);

    for _ in 0..item_count {
        // Read per-item header
        let aid = match read_u32_be(raw, &mut off) {
            Some(v) => v,
            None => { push_u32_be(&mut out, 0)?; break; }
        };
        let strategy_byte = match read_u8(raw, &mut off) {
            Some(v) => v,
            None => { push_u32_be(&mut out, 0)?; break; }
        };
        let strategy_full = strategy_byte != 0;
        let fact_len = match read_u32_be(raw, &mut off) {
            Some(v) => v as usize,
            None => { push_u32_be(&mut out, 0)?; break; }
        };
        if off + fact_len > raw.len() {
            push_u32_be(&mut out, 0)?;
            // Skip remaining – structural error, stop
            break;
        }
        let fact_bytes = &raw[off..off + fact_len];
        off += fact_len;

        // Compress fact (binary protocol, no JSON)
        let compressed_str = match compress_fact_inner(&compressor, fact_bytes) {
            Some(v) => match String::from_utf8(v) {
                Ok(s) => s,
                Err(_) => { push_u32_be(&mut out, 0)?; continue; }
            },
            None => { push_u32_be(&mut out, 0)?; continue; }
        };

        // ③ Pass compressed_str directly (no format!("{};{}", ...) in the common path).
        // ⑦ sig_buf is cleared and reused by auto_decompose_fill_sig on every call.
        let (ts_ref, vals) = match auto_decompose_fill_sig(&compressed_str, &mut sig_buf) {
            Some(v) => v,
            None => { push_u32_be(&mut out, 0)?; continue; }
        };
        // Copy timestamp to a 32-byte stack buffer (ASCII, ≤20 chars).
        let mut ts_buf = [0u8; 32];
        let ts_len = ts_ref.len().min(ts_buf.len());
        ts_buf[..ts_len].copy_from_slice(&ts_ref.as_bytes()[..ts_len]);

        // Apply fusion state (lock already held for whole batch)
        load_aid_registry_into_state(&mut fusion_state, aid, registry_root.as_deref());
        let encoded = match apply_fusion_state(&mut fusion_state, aid, strategy_full, &sig_buf, &vals) {
            Some(v) => v,
            None => { push_u32_be(&mut out, 0)?; continue; }
        };

        // ① parse_apply_blob now returns &[u8] — no to_vec() for DIFF body.
        let (cmd, tid, flags, body_native) = match parse_apply_blob(&encoded) {
            Some(v) => v,
            None => { push_u32_be(&mut out, 0)?; continue; }
        };
        if (flags & 0x03) != 0 {
            dump_aid_registry_from_state(&fusion_state, aid, registry_root.as_deref());
        }
        let ts_str = match std::str::from_utf8(&ts_buf[..ts_len]) {
            Ok(s) => s,
            Err(_) => { push_u32_be(&mut out, 0)?; continue; }
        };
        // ① DIFF path: finalize_packet receives body_native: &[u8] directly (0 alloc).
        // ③ FULL path: only now build "aid;compressed_str" (rare, < 5% of packets).
        let packet = if (flags & 0x04) != 0 {
            let mut aid_tmp = [0u8; 10];
            let aid_dec = u32_to_decimal_slice(aid, &mut aid_tmp);
            let mut full_body = Vec::with_capacity(aid_dec.len() + 1 + compressed_str.len());
            full_body.extend_from_slice(aid_dec);
            full_body.push(b';');
            full_body.extend_from_slice(compressed_str.as_bytes());
            match finalize_packet(cmd, aid, tid, ts_str, &full_body) {
                Some(v) => v,
                None => { push_u32_be(&mut out, 0)?; continue; }
            }
        } else {
            match finalize_packet(cmd, aid, tid, ts_str, body_native) {
                Some(v) => v,
                None => { push_u32_be(&mut out, 0)?; continue; }
            }
        };

        push_u32_be(&mut out, packet.len())?;
        out.extend_from_slice(&packet);
    }

    Some(out)
}

/// Batch pipeline: compress N facts + run fusion for each in one C ABI call.
///
/// Eliminates per-item Python↔Rust round-trips; acquires each registry lock
/// once per batch and holds the fusion state mutex for the whole batch.
///
/// Return value:
///   >0  bytes written to `out`
///   <0  required output size (caller should retry with -ret bytes)
///    0  structural error / invalid handles
///
/// # Safety
/// `input` must point to `input_len` readable bytes.
/// `out` must point to at least `out_len` writable bytes (may be null for size query).
#[no_mangle]
pub unsafe extern "C" fn os_pipeline_batch_v1(
    input: *const u8,
    input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    if input.is_null() || input_len == 0 {
        return 0;
    }
    let raw = std::slice::from_raw_parts(input, input_len);
    let result = match pipeline_batch_inner(raw) {
        Some(v) => v,
        None => return 0,
    };
    let needed = result.len();
    let needed_i32 = match i32::try_from(needed) {
        Ok(v) => v,
        Err(_) => return 0,
    };
    if out.is_null() || out_len < needed {
        return -needed_i32;
    }
    std::ptr::copy_nonoverlapping(result.as_ptr(), out, needed);
    needed_i32
}

// ─────────────────────────────────────────────────────────────────────────────
// Persistent fusion worker – zero-mutex single-item fuse path
// (compiled only when the "worker" feature is enabled; omitting it keeps the
//  hot-path DLL smaller and reduces icache pressure on pipeline_batch_inner)
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(feature = "worker")]
struct WorkerItem {
    input: Vec<u8>,
    reply: std::sync::mpsc::SyncSender<Vec<u8>>,
}

#[cfg(feature = "worker")]
struct WorkerHandle {
    sender: std::sync::mpsc::SyncSender<WorkerItem>,
}

#[cfg(feature = "worker")]
fn worker_registry() -> &'static Mutex<HashMap<u64, WorkerHandle>> {
    static REG: OnceLock<Mutex<HashMap<u64, WorkerHandle>>> = OnceLock::new();
    REG.get_or_init(|| Mutex::new(HashMap::new()))
}

#[cfg(feature = "worker")]
fn next_worker_id() -> u64 {
    static NEXT: AtomicU64 = AtomicU64::new(100_000_000);
    NEXT.fetch_add(1, Ordering::Relaxed)
}

/// Process one item: auto_decompose + apply_fusion + finalize_packet.
///
/// Input wire format: `u8(strategy) | u32_be(str_len) | utf8_bytes`
/// where utf8_bytes is exactly `raw_input` (e.g. `"42;DEVICE.OK.AAAA|..."`)
#[cfg(feature = "worker")]
fn worker_process_item(
    input: &[u8],
    registry_root: &Option<String>,
    fusion_state: &mut FusionState,
) -> Option<Vec<u8>> {
    let mut off = 0usize;
    let strategy_byte = read_u8(input, &mut off)?;
    let strategy_full = strategy_byte != 0;
    let str_len = read_u32_be(input, &mut off)? as usize;
    if off + str_len > input.len() {
        return None;
    }
    let raw_input = std::str::from_utf8(&input[off..off + str_len]).ok()?;
    let (ts, sig, vals) = auto_decompose_input_inner(raw_input)?;
    let aid = parse_src_aid(raw_input);
    load_aid_registry_into_state(fusion_state, aid, registry_root.as_deref());
    let encoded = apply_fusion_state(fusion_state, aid, strategy_full, &sig, &vals)?;
    // ① body_native: &[u8] borrow of encoded — no to_vec() needed in DIFF path.
    let (cmd, tid, flags, body_native) = parse_apply_blob(&encoded)?;
    if (flags & 0x03) != 0 {
        dump_aid_registry_from_state(fusion_state, aid, registry_root.as_deref());
    }
    // ts is &str borrowed from raw_input — pass directly, no String allocation needed
    if (flags & 0x04) != 0 {
        let full_body = raw_input.as_bytes().to_vec();
        finalize_packet(cmd, aid, tid, ts, &full_body)
    } else {
        finalize_packet(cmd, aid, tid, ts, body_native)
    }
}

#[cfg(feature = "worker")]
fn run_worker_thread(receiver: std::sync::mpsc::Receiver<WorkerItem>, registry_root: Option<String>) {
    let mut fusion_state = FusionState::default();
    loop {
        match receiver.recv() {
            Ok(item) => {
                let result = worker_process_item(&item.input, &registry_root, &mut fusion_state)
                    .unwrap_or_default();
                let _ = item.reply.send(result);
            }
            Err(_) => break,
        }
    }
}

/// Create a persistent fusion worker thread.
///
/// The worker owns a private `FusionState` (no global mutex per call).
/// Registry disk reads happen at most once per AID; writes only on template change.
///
/// Returns: worker handle (`u64 > 0`), or `0` on error.
///
/// # Safety
/// `registry_root` must point to `registry_root_len` valid UTF-8 bytes, or be null.
#[cfg(feature = "worker")]
#[no_mangle]
pub unsafe extern "C" fn os_worker_create_v1(
    _ctx_id: u64,
    registry_root: *const u8,
    registry_root_len: usize,
    queue_depth: u32,
) -> u64 {
    let reg_root: Option<String> = if registry_root.is_null() || registry_root_len == 0 {
        None
    } else {
        let bytes = std::slice::from_raw_parts(registry_root, registry_root_len);
        String::from_utf8(bytes.to_vec()).ok()
    };
    let depth = (queue_depth as usize).clamp(8, 65536);
    let (tx, rx) = sync_channel::<WorkerItem>(depth);
    let reg_root_clone = reg_root.clone();
    std::thread::spawn(move || run_worker_thread(rx, reg_root_clone));
    let handle_id = next_worker_id();
    match worker_registry().lock() {
        Ok(mut reg) => { reg.insert(handle_id, WorkerHandle { sender: tx }); }
        Err(_) => return 0,
    }
    handle_id
}

/// Submit one item to the worker and block until the binary packet is returned.
///
/// Input wire format: `u8(strategy) | u32_be(str_len) | utf8_str`
/// Returns bytes written (> 0), 0 for structural error, negative = required buf size.
///
/// # Safety
/// `input` / `out` must be valid pointers of the stated lengths.
#[cfg(feature = "worker")]
#[no_mangle]
pub unsafe extern "C" fn os_worker_submit_v1(
    worker_handle: u64,
    input: *const u8,
    input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    if input.is_null() || input_len == 0 {
        return 0;
    }
    let raw = std::slice::from_raw_parts(input, input_len).to_vec();
    let sender = {
        let reg = match worker_registry().lock() {
            Ok(v) => v,
            Err(_) => return 0,
        };
        match reg.get(&worker_handle) {
            Some(wh) => wh.sender.clone(),
            None => return 0,
        }
    };
    let (reply_tx, reply_rx) = sync_channel::<Vec<u8>>(1);
    if sender.send(WorkerItem { input: raw, reply: reply_tx }).is_err() {
        return 0;
    }
    let result = match reply_rx.recv() {
        Ok(v) => v,
        Err(_) => return 0,
    };
    if result.is_empty() {
        return 0;
    }
    let needed_i32 = match i32::try_from(result.len()) {
        Ok(v) => v,
        Err(_) => return 0,
    };
    if out.is_null() || out_len < result.len() {
        return -needed_i32;
    }
    std::ptr::copy_nonoverlapping(result.as_ptr(), out, result.len());
    needed_i32
}

/// Destroy a persistent worker and release its background thread.
///
/// Dropping the `WorkerHandle` drops the `SyncSender`, causing the worker
/// thread's `recv()` to return `Err` and exit cleanly.
///
/// # Safety
/// `worker_handle` must be a valid value returned by `os_worker_create_v1`.
#[cfg(feature = "worker")]
#[no_mangle]
pub unsafe extern "C" fn os_worker_destroy_v1(worker_handle: u64) {
    if let Ok(mut reg) = worker_registry().lock() {
        reg.remove(&worker_handle);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Placeholder JSON ABIs
// ─────────────────────────────────────────────────────────────────────────────

/// Placeholder JSON ABI export for standardize path.
#[no_mangle]
pub unsafe extern "C" fn os_standardize_json_v1(
    _input: *const u8,
    _input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    write_stub_json(out, out_len, br#"{}"#)
}

/// Placeholder JSON ABI export for handshake negotiate path.
#[no_mangle]
pub unsafe extern "C" fn os_handshake_negotiate_v1(
    _input: *const u8,
    _input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    write_stub_json(out, out_len, br#"{"ok":false,"error":"os_handshake_negotiate_v1_not_implemented"}"#)
}

/// Placeholder JSON ABI export for transporter send path.
#[no_mangle]
pub unsafe extern "C" fn os_transporter_send_v1(
    _input: *const u8,
    _input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    write_stub_json(out, out_len, br#"{"ok":false,"error":"os_transporter_send_v1_not_implemented"}"#)
}

/// Placeholder JSON ABI export for transporter listen path.
#[no_mangle]
pub unsafe extern "C" fn os_transporter_listen_v1(
    _input: *const u8,
    _input_len: usize,
    out: *mut u8,
    out_len: usize,
) -> i32 {
    write_stub_json(out, out_len, br#"{"ok":false,"error":"os_transporter_listen_v1_not_implemented"}"#)
}

