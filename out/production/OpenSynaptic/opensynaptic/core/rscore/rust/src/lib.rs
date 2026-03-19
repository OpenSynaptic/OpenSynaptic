//! OpenSynaptic RSCore – C-ABI native library.
//!
//! Exports the same symbols as the existing C libraries so that Python can
//! load this DLL through the existing `native_loader.py` / ctypes path.
//!
//! ABI-stable function signatures must remain identical to:
//!   - `src/opensynaptic/utils/base62/base62_native.c`  (Base62 codec)
//!   - CMD byte constants in `src/opensynaptic/core/pycore/handshake.py`

use std::ffi::c_char;
use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};
use base64::Engine;
use serde::{Deserialize, Serialize};

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

fn decode_ts_token_to_6bytes(ts_token: &str) -> Option<[u8; 6]> {
    let raw = b64_urlsafe_decode_nopad(ts_token)?;
    let mut ts6 = [0u8; 6];
    if raw.len() >= 6 {
        ts6.copy_from_slice(&raw[..6]);
        Some(ts6)
    } else {
        None
    }
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
    let device_id = read_string(input, &mut off)?;
    let dev_state = read_string(input, &mut off)?;
    let t_in = read_f64_be(input, &mut off)?;
    let sensor_count = read_u32_be(input, &mut off)? as usize;

    let mut sensors: Vec<(String, String, f64, String)> = Vec::with_capacity(sensor_count);
    for _ in 0..sensor_count {
        let sid = read_string(input, &mut off)?;
        let sst = read_string(input, &mut off)?;
        let val = read_f64_be(input, &mut off)?;
        let unit = read_string(input, &mut off)?;
        sensors.push((sid, sst, val, unit));
    }
    let geohash = read_opt_string(input, &mut off)?;
    let url = read_opt_string(input, &mut off)?;
    let msg = read_opt_string(input, &mut off)?;
    if off != input.len() {
        return None;
    }

    let t_raw = if state.use_ms && t_in < 100_000_000_000.0 {
        (t_in * 1000.0).trunc() as u64
    } else {
        t_in.trunc() as u64
    };
    let t_bytes = t_raw.to_be_bytes();
    let t_enc = base64_urlsafe_no_pad(&t_bytes[2..]);
    let s_sym = get_symbol(&state.states_map, &dev_state);

    let mut body = String::with_capacity(256 + sensors.len() * 24);
    body.push_str(&device_id);
    body.push('.');
    body.push_str(&s_sym);
    body.push('.');
    body.push_str(&t_enc);
    body.push('|');

    for (sid, sst, val, unit_raw) in sensors {
        let un = compress_unit(state, &unit_raw);
        let v = encode_b62_num(val, state.precision_val, true);
        let sst_sym = get_symbol(&state.states_map, &sst);
        body.push_str(&sid);
        body.push('>');
        body.push_str(&sst_sym);
        body.push('.');
        body.push_str(&un);
        body.push(':');
        body.push_str(&v);
        body.push('|');
    }

    if let Some(geo) = geohash {
        body.push('&');
        body.push_str(&geo);
        body.push('|');
    }
    if let Some(url_val) = url {
        let trimmed = url_val.strip_prefix("https://").unwrap_or(url_val.as_str());
        body.push('#');
        body.push_str(&base64_urlsafe_no_pad(trimmed.as_bytes()));
        body.push('|');
    }
    if let Some(msg_val) = msg {
        body.push('@');
        body.push_str(&base64_urlsafe_no_pad(msg_val.as_bytes()));
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

fn apply_fusion_state(
    state: &mut FusionState,
    src_aid: u32,
    strategy_full: bool,
    sig: Vec<u8>,
    vals_bin: Vec<Vec<u8>>,
) -> Option<Vec<u8>> {
    let aid_state = get_or_init_aid_state(state, src_aid);
    let mut new_template = false;
    let tid = match aid_state.sig_to_tid.get(&sig).copied() {
        Some(v) => v,
        None => {
            let tid = aid_state.next_tid;
            aid_state.next_tid = aid_state.next_tid.saturating_add(1);
            aid_state.sig_to_tid.insert(sig.clone(), tid);
            aid_state.tid_to_sig.insert(tid, sig);
            new_template = true;
            tid
        }
    };
    let tid_vals = aid_state.runtime_vals.entry(tid).or_default();
    let mut runtime_changed = false;

    if strategy_full {
        if tid_vals.len() != vals_bin.len() || *tid_vals != vals_bin {
            *tid_vals = vals_bin;
            runtime_changed = true;
        }
        let mut flags = 0u8;
        if new_template { flags |= 0x01; }
        if runtime_changed { flags |= 0x02; }
        flags |= 0x04; // use raw_input body
        return pack_fusion_result(DATA_FULL, tid, flags, &[]);
    }

    if tid_vals.len() != vals_bin.len() {
        *tid_vals = vals_bin;
        runtime_changed = true;
        let mut flags = 0u8;
        if new_template { flags |= 0x01; }
        if runtime_changed { flags |= 0x02; }
        flags |= 0x04; // use raw_input body
        return pack_fusion_result(DATA_FULL, tid, flags, &[]);
    }

    let mut mask: u128 = 0;
    let mut diff_body: Vec<u8> = Vec::new();
    let mut changed = false;
    for (i, v) in vals_bin.iter().enumerate() {
        if tid_vals.get(i)? != v {
            if i >= 128 {
                return None;
            }
            mask |= 1u128 << i;
            let v_len = u8::try_from(v.len()).ok()?;
            diff_body.push(v_len);
            diff_body.extend_from_slice(v);
            tid_vals[i] = v.clone();
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
    let mut body = Vec::with_capacity(mask_len + diff_body.len());
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
pub unsafe extern "C" fn os_crc16_ccitt_pub(
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

fn auto_decompose_input_inner(input: &str) -> Option<(Vec<u8>, Vec<u8>, Vec<Vec<u8>>)> {
    let work = match input.split_once(';') {
        Some((_, tail)) => tail,
        None => input,
    };
    let (head, payload) = work.split_once('|')?;
    let (h_base, ts_str) = head.rsplit_once('.')?;

    let mut raw_vals: Vec<Vec<u8>> = Vec::new();
    let mut sig_segments: Vec<String> = Vec::new();

    for seg in payload.split('|') {
        if seg.is_empty() {
            continue;
        }
        if let Some((tag, content)) = seg.split_once('>') {
            if let Some((meta, val)) = content.rsplit_once(':') {
                raw_vals.push(meta.as_bytes().to_vec());
                raw_vals.push(val.as_bytes().to_vec());
                sig_segments.push(format!("{}>\x01:\x01", tag));
                continue;
            }
        }
        sig_segments.push(seg.to_string());
    }

    let full_sig = format!("{}.{{TS}}|{}|", h_base, sig_segments.join("|")).into_bytes();
    Some((ts_str.as_bytes().to_vec(), full_sig, raw_vals))
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
    encoded.extend_from_slice(&ts);
    encoded.extend_from_slice(&full_sig);
    for v in &vals {
        if push_u32_be(&mut encoded, v.len()).is_none() {
            return 0;
        }
        encoded.extend_from_slice(v);
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
        match apply_fusion_state(&mut state, src_aid, strategy_full, sig, vals) {
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
    const VER: &[u8] = b"opensynaptic_rscore/0.1.0\0";
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
}

#[derive(Debug, Deserialize)]
struct FusionDecompressReq {
    #[serde(default)]
    ctx_id: u64,
    packet_b64: String,
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

fn parse_apply_blob(encoded: &[u8]) -> Option<(u8, u32, u8, Vec<u8>)> {
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
    Some((cmd, tid, flags, encoded[10..10 + body_len].to_vec()))
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
        match apply_fusion_state(&mut state, src_aid, strategy_full, sig, vals) {
            Some(v) => v,
            None => return 0,
        }
    };
    let (cmd, tid, flags, body_native) = match parse_apply_blob(&encoded) {
        Some(v) => v,
        None => return 0,
    };

    let body = if (flags & 0x04) != 0 {
        req.raw_input.as_bytes().to_vec()
    } else {
        body_native
    };
    let ts_str = match String::from_utf8(ts) {
        Ok(v) => v,
        Err(_) => return 0,
    };
    let packet = match finalize_packet(cmd, src_aid, tid, &ts_str, &body) {
        Some(v) => v,
        None => return 0,
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
                let aid_state = get_or_init_aid_state(&mut state, source_aid);
                aid_state.sig_to_tid.insert(sig.clone(), tid);
                aid_state.tid_to_sig.insert(tid, sig);
                aid_state.runtime_vals.insert(tid, vals);
                aid_state.next_tid = aid_state.next_tid.max(tid.saturating_add(1));
            }
        }
        p
    } else if base_cmd == DATA_DIFF || base_cmd == DATA_HEART {
        let resolved = {
            let mut state = match arc.lock() {
                Ok(v) => v,
                Err(_) => return 0,
            };
            match apply_fusion_receive_state(&mut state, source_aid, base_cmd, tid, ts_enc.into_bytes(), body) {
                Some(v) => v,
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

        // Build raw_input string used by decompose + fusion
        let raw_input = format!("{};{}", aid, compressed_str);

        // Auto-decompose into (ts, sig, vals)
        let (ts, sig, vals) = match auto_decompose_input_inner(&raw_input) {
            Some(v) => v,
            None => { push_u32_be(&mut out, 0)?; continue; }
        };

        // Apply fusion state (lock already held for whole batch)
        let encoded = match apply_fusion_state(&mut fusion_state, aid, strategy_full, sig, vals) {
            Some(v) => v,
            None => { push_u32_be(&mut out, 0)?; continue; }
        };

        // Decode apply-blob and build packet
        let (cmd, tid, flags, body_native) = match parse_apply_blob(&encoded) {
            Some(v) => v,
            None => { push_u32_be(&mut out, 0)?; continue; }
        };
        let ts_str = match String::from_utf8(ts) {
            Ok(v) => v,
            Err(_) => { push_u32_be(&mut out, 0)?; continue; }
        };
        let body = if (flags & 0x04) != 0 {
            raw_input.into_bytes()
        } else {
            body_native
        };
        let packet = match finalize_packet(cmd, aid, tid, &ts_str, &body) {
            Some(v) => v,
            None => { push_u32_be(&mut out, 0)?; continue; }
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

