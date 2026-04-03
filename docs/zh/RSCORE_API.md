---
layout: default
title: Rscore API 设计 – OpenSynaptic Rust 核心
language: zh
---

# Rscore API 设计 — OpenSynaptic Rust 核心

**目的**：定义 `rscore/` 的完整 Rust API — `pycore/` 的原生 Rust 重新实现。  
**真实来源**：`docs/internal/PYCORE_INTERNALS.md`  
**目标 crate 路径**：`src/opensynaptic/core/rscore/`  
**语言**：Rust（版本 2021）  
**FFI 表面**：通过 `pyo3` 可从 Python 调用；也可用作独立的 `no_std` 兼容库。

---

## 目录

1. [库布局](#1-库布局)
2. [Cargo.toml 依赖项](#2-cargotoml-依赖项)
3. [数据类型（共享）](#3-数据类型共享)
4. [模块：`security`](#4-模块security)
5. [模块：`codec`（Base62）](#5-模块codecbase62)
6. [模块：`standardizer`](#6-模块standardizer)
7. [模块：`engine`（Solidity）](#7-模块enginesolidity)
8. [PyO3 绑定层](#8-pyo3-绑定层)
9. [配置映射](#9-配置映射)
10. [错误类型](#10-错误类型)

---

## 1. 库布局

```
src/opensynaptic/core/rscore/
├── Cargo.toml
├── build.rs                  # 可选：编译 C 安全/编解码垫片
├── src/
│   ├── lib.rs                # crate 根；重新导出 + PyO3 模块初始化
│   ├── error.rs              # OsError 枚举
│   ├── config.rs             # OsConfig、EngineSettings、SecuritySettings、Resources
│   ├── security.rs           # crc8、crc16、derive_session_key、xor_payload
│   ├── codec.rs              # Base62Codec、b62_encode、b62_decode
│   ├── standardizer.rs       # UnitRegistry、Standardizer、SensorFact
│   ├── engine.rs             # SolidityEngine、compress、decompress
│   ├── fusion.rs             # FusionEngine、run_engine、decompress
│   ├── handshake.rs          # Cmd、HandshakeManager、SecureSession
│   ├── transport.rs          # Transporter trait、TransportKind
│   ├── node.rs               # OpenSynapticNode（编排器）
│   └── py_bindings.rs        # #[pymodule] rscore + #[pyclass] 包装器
```

---

## 2. Cargo.toml 依赖项

```toml
[package]
name        = "opensynaptic-rscore"
version     = "0.1.0"
edition     = "2021"

[lib]
name        = "rscore"
crate-type  = ["cdylib", "rlib"]

[dependencies]
# 序列化
serde       = { version = "1", features = ["derive"] }
serde_json  = "1"

# 零复制字节缓冲区
bytes       = "1"

# Base64（URL 安全，无填充）
base64      = "0.22"

# 并行/并发原语
parking_lot = "0.12"       # RwLock / Mutex 无中毒

# derive_session_key 的哈希
blake2      = "0.10"
sha2        = "0.10"

# CRC
crc         = "3"

# 文件系统助手
walkdir     = "2"

# PyO3 桥接（可选功能）
pyo3        = { version = "0.21", features = ["extension-module"], optional = true }

[features]
default    = ["python"]
python     = ["pyo3"]
no_std_compat = []     # 剥离 serde_json / walkdir 用于嵌入式目标

[profile.release]
opt-level = 3
lto       = true
```

---

## 3. 数据类型（共享）

### 3.1 `SensorFact`

```rust
/// 由 Standardizer 生成并由 SolidityEngine 使用的规范化传感器事实。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SensorFact {
    /// 设备标识符字符串
    pub id: String,
    /// 设备状态（例如"ONLINE"）
    pub s: String,
    /// UNIX 时间戳（秒）
    pub t: u64,
    /// 可变长度传感器槽
    pub sensors: Vec<SensorSlot>,
    /// 可选的地理哈希
    pub geohash: Option<String>,
    /// 可选的资源 URL（完整，带 https://）
    pub url: Option<String>,
    /// 可选的补充消息
    pub msg: Option<String>,
}

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SensorSlot {
    pub id: String,
    /// 传感器状态字符串
    pub status: String,
    /// 规范化的 SI 值
    pub value: f64,
    /// 物理属性字符串，例如"Pressure"、"Length/Time"
    pub unit: String,
}
```

### 3.2 `BinaryFrame`

```rust
/// 由 FusionEngine 生成的编码线路数据包。
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

---

## 4. 模块：`security`

**文件**：`src/security.rs`  
**映射自**：`utils/security/security_core.py` + `security_native.c`

```rust
use bytes::Bytes;

/// CRC-8（多项式 = 0x07，初始 = 0x00）
pub fn crc8(data: &[u8]) -> u8;
pub fn crc8_with(data: &[u8], poly: u8, init: u8) -> u8;

/// CRC-16/CCITT（多项式 = 0x1021，初始 = 0xFFFF）
pub fn crc16_ccitt(data: &[u8]) -> u16;
pub fn crc16_ccitt_with(data: &[u8], poly: u16, init: u16) -> u16;

/// 从 (device_id, timestamp_raw) 派生 32 字节会话密钥。
/// Python：derive_session_key(assigned_id, timestamp_raw)
/// 实现方式：BLAKE2b-256( aid.to_le_bytes() ++ ts.to_le_bytes() )
pub fn derive_session_key(aid: u64, timestamp_raw: u64) -> [u8; 32];

/// XOR 流密码与密钥偏移量 nonce。
/// offset = crc8_val & 0x1F  （匹配 Python：crc8_val & 31）
pub fn xor_payload(payload: &[u8], key: &[u8], offset: u32) -> Bytes;

/// 零复制变体：将 XOR 结果写入 out_buf。
/// 返回写入的字节数。
/// 前置条件：out_buf.len() >= payload.len()
pub fn xor_payload_into(payload: &[u8], key: &[u8], offset: u32, out_buf: &mut [u8]) -> usize;
```

---

## 5. 模块：`codec`（Base62）

**文件**：`src/codec.rs`  
**映射自**：`utils/base62/base62.py` + `base62_native.c`

```rust
pub const CHARS: &[u8; 62] =
    b"0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";

/// 具有固定点精度的 Base62 编解码器。
pub struct Base62Codec {
    precision: u8,
    precision_val: i64,   // 10^precision
}

impl Base62Codec {
    pub fn new(precision: u8) -> Self;

    /// 使用固定点缩放编码浮点数：round(n * 10^precision) → Base62。
    pub fn encode(&self, n: f64) -> String;

    /// 编码原始整数而不缩放。
    pub fn encode_raw(&self, n: i64) -> String;

    /// 解码 Base62 字符串并除以 10^precision。
    pub fn decode(&self, s: &str) -> Result<f64, OsError>;

    /// 解码而不除（原始整数）。
    pub fn decode_raw(&self, s: &str) -> Result<i64, OsError>;
}

// 模块级助手（使用默认精度=4 编解码器）
pub fn b62_encode(n: f64, precision: u8) -> String;
pub fn b62_decode(s: &str, precision: u8) -> Result<f64, OsError>;
pub fn b62_encode_raw(n: i64) -> String;
pub fn b62_decode_raw(s: &str) -> Result<i64, OsError>;
```

**编码算法**：

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

## 6. 模块：`standardizer`

**文件**：`src/standardizer.rs`  
**映射自**：`pycore/standardization.py`

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
    sorted_prefix_keys: Vec<String>,      // 按长度降序排序
    unit_cache: parking_lot::RwLock<HashMap<String, UnitLaw>>,
    lib_units_dir: PathBuf,
    cache_path: PathBuf,
    is_dirty: AtomicBool,
}

impl Standardizer {
    /// 从磁盘加载配置和单位库。
    pub fn new(config: &OsConfig, base_dir: &Path) -> Result<Self, OsError>;

    /// 从磁盘加载持久化的单位缓存。
    pub fn load_cache(&mut self) -> Result<(), OsError>;

    /// 如果脏，将单位缓存持久化到磁盘。
    pub fn save_cache(&self) -> Result<(), OsError>;

    /// 主管道入口点：规范化原始传感器读数。
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

    /// 解析单位字符串到其 UnitLaw。
    /// 检查缓存 → 库扫描 → 前缀剥离。
    pub fn resolve_unit_law(&self, unit_str: &str) -> Option<UnitLaw>;

    /// 将任何新解析的单位持久化到缓存（防抖）。
    pub fn flush_if_dirty(&self) -> Result<(), OsError>;
}
```

---

## 7. 模块：`engine`（Solidity）

**文件**：`src/engine.rs`  
**映射自**：`pycore/solidity.py`

```rust
pub struct SolidityEngine {
    codec:           Base62Codec,
    use_ms:          bool,
    units_map:       HashMap<String, String>,   // 小写 ucum → 符号代码
    states_map:      HashMap<String, String>,   // 小写状态 → 代码
    unit_token_cache: parking_lot::Mutex<LruCache<String, String>>,
    b62_encode_cache: parking_lot::Mutex<LruCache<(u8, i64), String>>,
}

impl SolidityEngine {
    pub fn new(config: &OsConfig, base_dir: &Path) -> Result<Self, OsError>;

    /// 将 SensorFact 压缩到线路文本格式。
    pub fn compress(&self, fact: &SensorFact) -> String;

    /// 将线路文本格式解压回 SensorFact。
    pub fn decompress(&self, s: &str) -> Result<SensorFact, OsError>;

    /// 使用固定点精度将浮点数编码为 Base62。
    pub fn encode_b62(&self, n: f64, use_precision: bool) -> String;

    /// 将 Base62 字符串解码为浮点数。
    pub fn decode_b62(&self, s: &str, use_precision: bool) -> Result<f64, OsError>;
}
```

---

## 8. PyO3 绑定层

所有公开结构通过 `#[pyclass]` 宏包装，以便与 Python 代码互操作。

---

## 9. 配置映射

Rscore 从 `OsConfig`（通过 JSON 反序列化）读取相同的配置键，映射与 pycore 完全相同。

---

## 10. 错误类型

```rust
#[derive(Debug)]
pub enum OsError {
    Io(std::io::Error),
    Json(serde_json::error::Error),
    Codec(String),
    Security(String),
    Config(String),
    Invalid(String),
}

impl std::fmt::Display for OsError { ... }
impl std::error::Error for OsError { ... }
```

> **注意**：此文档涵盖了 Rscore API 的关键模块和数据结构。有关完整的详细实现和线路协议说明，请参考源代码注释和测试。
