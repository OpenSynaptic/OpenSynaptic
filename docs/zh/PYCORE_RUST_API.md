---
layout: default
title: Pycore → Rscore Rust API 规范
language: zh
---

# Pycore → Rscore Rust API 规范

此文档定义了 Rust 端 API 约定，必须与 `src/opensynaptic/core/pycore/` 在行为上兼容。

---

## 实现状态

| 阶段 | 描述 | 状态 |
|------|------|------|
| 1 – 垫片 | `rscore` 插件导出 pycore 兼容的 Python 符号 | ✅ 完成 |
| 2 – 混合 | Rust 处理 Base62 编解码 + CMD 帮助程序；Python 保持编排 | ✅ 完成 |
| 3 – 原生 | Rust 数据包构建/解析替换 Python 热循环，具有黄金向量奇偶校验 | 🔲 计划中 |

---

## 范围

- 保持 `opensynaptic.core` 公共符号不变。
- 允许 `engine_settings.core_backend = "rscore"` 可选加入，无需更改用户代码。
- 保留 `OSHandshakeManager`/`OSVisualFusionEngine` 使用的命令字节和数据包语义。

---

## 公共符号奇偶校验

rscore 插件公开与 pycore 相同的符号名称：

| 符号 | 阶段 2 实现 |
|------|-----------|
| `OpenSynaptic` | pycore 垫片 |
| `OpenSynapticStandardizer` | pycore 垫片 |
| `OpenSynapticEngine` | **混合** – DLL 存在时 `self.codec = RsBase62Codec` |
| `OSVisualFusionEngine` | pycore 垫片 |
| `OSHandshakeManager` | pycore 垫片 |
| `CMD` | pycore 常数类（线路值冻结） |
| `TransporterManager` | pycore 垫片 |

---

## Rust 库

位置：`src/opensynaptic/core/rscore/rust/`

```
Cargo.toml          – cdylib，发布配置 O3+strip
src/lib.rs          – 所有 C-ABI #[no_mangle] 导出
```

构建输出：`src/opensynaptic/utils/c/bin/os_rscore.dll` (Windows)，
`os_rscore.so` (Linux)，`os_rscore.dylib` (macOS)。

---

## 已实现的 C-ABI 导出

这些是 `os_rscore` 中的 **实时** 符号（阶段 2）：

```rust
// Base62 编解码（与 base62_native.c 逐字节相同的语义）
pub unsafe extern "C" fn os_b62_encode_i64(value: i64, out: *mut c_char, out_len: usize) -> i32;
pub unsafe extern "C" fn os_b62_decode_i64(s: *const c_char, ok: *mut i32) -> i64;

// CMD 字节帮助程序
pub extern "C" fn os_cmd_is_data(cmd: u8) -> i32;
pub extern "C" fn os_cmd_normalize_data(cmd: u8) -> u8;
pub extern "C" fn os_cmd_secure_variant(cmd: u8) -> u8;

// 元数据
pub unsafe extern "C" fn os_rscore_version(out: *mut c_char, out_len: usize) -> i32;
```

---

## 命令字节约定（`CMD`）

线路级值是不可变的。任何更改都是 **破坏协议的更改**。

| 名称 | 值 |
|------|---:|
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

## Python 绑定（`rscore/codec.py`）

```python
from opensynaptic.core.rscore.codec import (
    RsBase62Codec,     # utils.base62.base62.Base62Codec 的替代品
    has_rs_native,     # bool – DLL 存在？
    rs_version,        # str  – "opensynaptic_rscore/0.1.0"
    cmd_is_data,       # (int) -> bool
    cmd_normalize_data,# (int) -> int  安全→普通直通
    cmd_secure_variant,# (int) -> int  普通→安全直通
)
```

---

## 精度约定

`RsBase62Codec(precision=p)` 必须与来自 `utils.base62.base62` 的 `Base62Codec(precision=p)` 相同地编码/解码。  
黄金向量奇偶校验在 `TestRscore.test_rs_codec_parity_with_c_codec` 中强制执行。

精度来自 `engine_settings.precision`（默认 4 → `precision_val = 10000`）。

---

## 推出阶段（详细）

### 阶段 3 – 原生（计划中）

实现后，以下 Python 热循环将被替换：

```rust
// 数据包头构建
pub fn os_parse_header(packet: &[u8]) -> Result<PacketHeader, OsError>;
pub fn os_build_header(aid: u32, status: u8, timestamp_ms: u64, out: &mut [u8]) -> Result<usize, OsError>;

// CRC 帮助程序（已在 os_security 中；迁移到 os_rscore 用于单个库）
pub fn os_crc16_ccitt(data: &[u8], poly: u16, init: u16) -> u16;
```

---

## 开发者工作流程

**构建 Rust DLL：**
```powershell
# 独立
python -u src/opensynaptic/core/rscore/build_rscore.py

# 通过 CLI
python -u src/main.py rscore-build

# 与 C 目标一起
python -u src/main.py native-build --include-rscore
```

**检查 Rust DLL 状态：**
```powershell
python -u src/main.py rscore-check
python -u src/main.py rscore-check --json
```

**将活动核心切换到 rscore：**
```json
// Config.json
"engine_settings": { "core_backend": "rscore" }
```
或设置环境变量：`OPENSYNAPTIC_CORE=rscore`

**运行奇偶校验测试：**
```powershell
$env:PYTHONPATH="src;."
py -3 -m unittest opensynaptic.services.test_plugin.component_tests.TestRscore
py -3 -m unittest opensynaptic.services.test_plugin.component_tests.TestRscoreEngine
```

---

## 兼容性规则

- `assigned_id == 4294967295` 仍是未分配的哨兵。
- 所有状态映射中的传输器键都是小写。
- 时间戳编码（`use_ms`、`time_precision`、`epoch_base`）必须与 pycore 往返。
- `compress(fact)` 输出在 pycore 和 rscore 引擎之间**必须逐字节相同**。

---

## 验证矩阵

在生产环境中启用 `core_backend=rscore` 之前：

| 检查 | 测试类 | 状态 |
|------|--------|------|
| `rscore` 可被 `CoreManager` 发现 | `TestCoreManager.test_rscore_discovered` | ✅ |
| `rscore` 可被 `CoreManager` 加载 | `TestCoreManager.test_rscore_loadable` | ✅ |
| 构建后 `has_rs_native()` 返回 True | `TestRscore.test_has_rs_native_returns_true` | ✅ |
| `RsBase62Codec` 往返 | `TestRscore.test_rs_codec_roundtrip` | ✅ |
| Rust 与 C Base62 字节奇偶性 | `TestRscore.test_rs_codec_parity_with_c_codec` | ✅ |
