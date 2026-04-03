---
layout: default
title: 核心 API 指南
language: zh
---

# 核心 API 指南

**语言**: [English](../CORE_API.md) | [中文](CORE_API.md)

本文档描述硬切换核心 API。

> **另见**：
> - [`API.md`](API.md) - 完整的公共 API 参考（包括服务和插件）
> - [English ARCHITECTURE.md](../ARCHITECTURE.md) - 架构详解
> - [English RSCORE_API.md](../RSCORE_API.md) - Rust 核心 API

---

## 公共核心接口

仅从 `opensynaptic.core` 导入：

```python
from opensynaptic.core import (
    get_core_manager,
    OpenSynaptic,
    OpenSynapticStandardizer,
    OpenSynapticEngine,
    OSVisualFusionEngine,
    OSHandshakeManager,
    TransporterManager,
    CMD,
)
```

仅导出核心符号。服务/插件内部不重新导出。

`get_core_manager()` 是用于发现和选择核心插件的管理入口点。

---

## 核心布局（硬切换）

- 核心实现包：`src/opensynaptic/core/pycore/`
- 公共外观包：`src/opensynaptic/core/__init__.py`
- 核心插件管理器：`src/opensynaptic/core/coremanager.py`
- 惰性插件注册表：`src/opensynaptic/core/loader.py`

### 示例

```python
from opensynaptic.core import OpenSynaptic, get_core_manager

# 初始化节点
node = OpenSynaptic(config_path='Config.json')

# 管理核心
manager = get_core_manager()
print(manager.available_cores())      # ['pycore', 'rscore']
manager.set_active_core('pycore')
```

---

## 本地C（ctypes）加速

`base62.py` 和 `security_core.py` 是仅本地的 ctypes 绑定。

- 源文件：`src/opensynaptic/utils/base62/base62_native.c`
- 输出：`os_base62.dll` / `.so` / `.dylib`
- 本地加载器：`src/opensynaptic/utils/c/native_loader.py`

### 手动构建本地库

```powershell
python -u src/main.py native-check
python -u src/main.py native-build
```

### 禁用运行时自动构建

```powershell
$env:OPENSYNAPTIC_AUTO_BUILD_NATIVE = "0"
```

### 启用自动构建（显式）

```powershell
$env:OPENSYNAPTIC_AUTO_BUILD_NATIVE = "1"
```

### 设置自定义本地二进制目录

```powershell
$env:OPENSYNAPTIC_NATIVE_DIR = "E:\path\to\native\bin"
```

---

## `OpenSynaptic` 类

主要协调类。

### 初始化

```python
node = OpenSynaptic(config_path: str | None = None)
```

**关键属性**：

| 属性 | 类型 | 说明 |
|------|------|------|
| `config` | `dict` | 加载的 Config.json 内容 |
| `assigned_id` | `int \| None` | 当前设备 ID（`4294967295` = 未分配） |
| `device_id` | `str` | 人类可读的设备标识符 |
| `standardizer` | `OpenSynapticStandardizer` | 标准化子系统 |
| `engine` | `OpenSynapticEngine` | Base62 压缩子系统 |
| `fusion` | `OSVisualFusionEngine` | 二进制数据包编码/解码子系统 |
| `transporter_manager` | `TransporterManager` | 可插拔传输器注册表 |

### 关键方法

#### `ensure_id(server_ip, server_port, device_meta=None, timeout=5.0) → bool`

通过 UDP 从服务器请求 `uint32` 设备 ID。  
将分配的 ID 持久化回 `Config.json`。  
成功获得 ID 或已存在时返回 `True`。

#### `transmit(sensors, device_id=None, device_status='ONLINE', **kwargs) → tuple[bytes, int, str]`

完整管道：标准化 → 压缩 → 融合为二进制数据包。  
如果 `assigned_id` 未设置，抛出 `RuntimeError`。

**参数**：
- `sensors`: `list[list]` - `[[sensor_id, status, value, unit], ...]`
- `device_id`: `str | None` - 覆盖设备标识符
- `device_status`: `str` - 设备状态字符串，例如 `"ONLINE"`

**返回**：`(binary_packet, assigned_id, strategy_label)` 其中 `strategy_label` 是 `"FULL_PACKET"` 或 `"DIFF_PACKET"`。

#### `dispatch(packet, medium=None) → bool`

通过指定的传输介质分发数据包。

**参数**：
- `packet`: `bytes` - 二进制数据包
- `medium`: `str | None` - 传输方式（`"UDP"`、`"MQTT"` 等）；如果 `None`，使用 `Config.json` 中的默认值

---

## `get_core_manager()` 函数

获取核心管理器以发现和切换后端。

```python
from opensynaptic.core import get_core_manager

manager = get_core_manager()

# 列出可用核心
available = manager.available_cores()  # ['pycore', 'rscore']

# 设置活跃核心
manager.set_active_core('rscore')

# 获取符号
OpenSynaptic = manager.get_symbol('OpenSynaptic')
```

---

## 向后兼容性说明

⚠️ **中大的改变**：
- 已移除 `opensynaptic.core.core`、`opensynaptic.core.solidity` 等导入路径
- **仅使用** `opensynaptic.core` 导出
- Base62 和安全逻辑不再有 Python 算法回退；这些代码路径需要本地库

---

## 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `OPENSYNAPTIC_CORE` | 强制活跃核心 | `OPENSYNAPTIC_CORE=rscore` |
| `OPENSYNAPTIC_AUTO_BUILD_NATIVE` | 启用/禁用自动本地构建 | `OPENSYNAPTIC_AUTO_BUILD_NATIVE=1` |
| `OPENSYNAPTIC_NATIVE_DIR` | 自定义本地二进制目录 | `OPENSYNAPTIC_NATIVE_DIR=E:\bin` |

---

**语言**: [English](../CORE_API.md) | [中文](CORE_API.md)  
**最后更新**: 2026-04-04
