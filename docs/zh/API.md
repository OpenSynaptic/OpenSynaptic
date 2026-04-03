---
layout: default
title: OpenSynaptic API 参考
language: zh
---

# OpenSynaptic API 参考

**语言**: [English](../API.md) | [中文](API.md)  
**最后更新**: 2026-04-04

当前在存储库中实现的 API 和服务合约。

> **深度参考**：
> - [`CORE_API.md`](CORE_API.md) - 核心 API 选择和加载器参考
> - [`CONFIG_SCHEMA.md`](CONFIG_SCHEMA.md) - `Config.json` 架构参考
> - [`TRANSPORTER_PLUGIN.md`](../TRANSPORTER_PLUGIN.md)（英文）- 如何添加新的传输器驱动程序

---

## `OpenSynaptic` — 顶级协调器

位置：`src/opensynaptic/core/pycore/core.py`（通过 `opensynaptic.core` 导出）

主要协调器。实例化它会从 `Config.json` 连接所有子系统。

### 构造函数

```python
OpenSynaptic(config_path: str | None = None)
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `config_path` | `str \| None` | `Config.json` 的可选路径（绝对或相对）。如果 `None`，`OSContext` 自动检测项目根并加载默认配置。 |

### 关键属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `config` | `dict` | 加载的 `Config.json` 内容 |
| `config_path` | `str` | 实例使用的活跃配置路径 |
| `base_dir` | `str` | 项目根目录 |
| `assigned_id` | `int \| None` | 当前设备 ID（`4294967295` = 未分配） |
| `device_id` | `str` | 人类可读的设备标识符 |
| `standardizer` | `OpenSynapticStandardizer` | 标准化子系统 |
| `engine` | `OpenSynapticEngine` | Base62 压缩子系统 |
| `fusion` | `OSVisualFusionEngine` | 二进制数据包编码/解码子系统 |
| `protocol` | `OSHandshakeManager` | CMD 分发和会话管理器 |
| `id_allocator` | `IDAllocator` | 服务器端 ID 池管理器 |
| `transporter_manager` | `TransporterManager` | 可插拔传输器注册表 |
| `active_transporters` | `dict[str, driver]` | 当前启用的传输驱动程序 |
| `service_manager` | `ServiceManager` | 插件挂载/生命周期管理器 |
| `db_manager` | `DatabaseManager \| None` | SQL 引擎（如果配置） |

### 主要方法

#### `ensure_id(server_ip, server_port, device_meta=None, timeout=5.0) → bool`

通过 UDP 从服务器请求 `uint32` 设备 ID（`CMD.ID_REQUEST`）。  
将分配的 ID 持久化回 `Config.json`。  
成功获得 ID 或已存在时返回 `True`。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `server_ip` | `str` | 必需 | 服务器主机名或 IP |
| `server_port` | `int` | 必需 | UDP 服务器端口 |
| `device_meta` | `dict \| None` | `None` | 随请求一起发送的可选元数据 |
| `timeout` | `float` | `5.0` | 套接字超时（秒） |

#### `ensure_time(server_ip=None, server_port=None, timeout=3.0) → int | None`

将本地时钟与服务器的 UNIX 时间戳同步。  
返回服务器时间戳（int）或失败时返回 `None`。

#### `transmit(sensors, device_id=None, device_status='ONLINE', **kwargs) → tuple[bytes, int, str]`

完整管道：标准化 → 压缩 → 融合为二进制数据包。  
如果 `assigned_id` 未设置，抛出 `RuntimeError`。

| 参数 | 类型 | 说明 |
|------|------|------|
| `sensors` | `list[list]` | `[[sensor_id, status, value, unit], ...]` |
| `device_id` | `str \| None` | 覆盖设备标识符（默认为 `self.device_id`） |
| `device_status` | `str` | 设备状态字符串，例如 `"ONLINE"` |

返回 `(binary_packet, assigned_id, strategy_label)` 其中 `strategy_label` 是 `"FULL_PACKET"` 或 `"DIFF_PACKET"`。

#### `dispatch(packet, medium=None) → bool`

通过指定的传输介质分发数据包。

| 参数 | 类型 | 说明 |
|------|------|------|
| `packet` | `bytes` | 二进制数据包 |
| `medium` | `str \| None` | 传输方式（`"UDP"`、`"TCP"`、`"MQTT"` 等）；如果 `None`，使用 Config.json 默认值 |

---

## `OpenSynapticStandardizer` — UCUM 标准化

将所有传感器读数转换为统一的 UCUM 单位。

```python
standardizer = node.standardizer
standardized = standardizer.standardize(sensors, **options)
# 返回标准化的传感器列表
```

---

## `OpenSynapticEngine` — Base62 压缩

利用 Base62 编码压缩传感器数据。

```python
engine = node.engine
compressed = engine.compress(standardized_data)
# 返回压缩的 Base62 字符串或字节
```

---

## `OSVisualFusionEngine` — 二进制打包和融合

将标准化和压缩的数据融合成高效的二进制数据包。

```python
fusion = node.fusion
packet, metadata = fusion.run_engine(compressed_data, device_meta)
# 返回 (binary_packet, metadata_dict)
```

支持两种策略：
- **FULL_PACKET**: 完整数据快照
- **DIFF_PACKET**: 仅变化的字段（增量更新）

---

## `TransporterManager` — 可插拔传输

发现、加载和管理传输驱动程序。

```python
manager = node.transporter_manager
manager.list_drivers()           # 列出可用驱动程序
manager.enable("udp")            # 启用 UDP 传输
manager.disable("mqtt")          # 禁用 MQTT 传输
manager.send(packet, medium="udp")
```

---

## 使用示例

### 最小化示例

```python
from opensynaptic.core import OpenSynaptic

node = OpenSynaptic()
node.ensure_id("192.168.1.100", 8080)

sensors = [
    ["temperature", "OK", 23.5, "degC"],
    ["humidity", "OK", 65.0, "%RH"],
]

packet, aid, strategy = node.transmit(sensors=sensors)
print(f"发送完成：{len(packet)} 字节，策略：{strategy}")

node.dispatch(packet, medium="UDP")
```

### 使用多个传输

```python
from opensynaptic.core import OpenSynaptic

node = OpenSynaptic()

# 通过 UDP 和 MQTT 同时分发
for medium in ["UDP", "MQTT"]:
    success = node.dispatch(packet, medium=medium)
    print(f"{medium}: {'成功' if success else '失败'}")
```

### 核心管理

```python
from opensynaptic.core import get_core_manager

manager = get_core_manager()

# 列出可用核心
print(manager.available_cores())

# 切换到 Rust 核心
manager.set_active_core('rscore')

# 获取 OpenSynaptic 类
OpenSynaptic = manager.get_symbol('OpenSynaptic')
node = OpenSynaptic()
```

---

## 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `OPENSYNAPTIC_CORE` | 强制活跃核心 | `OPENSYNAPTIC_CORE=rscore` |
| `OPENSYNAPTIC_CONFIG` | 强制 Config.json 路径 | `OPENSYNAPTIC_CONFIG=/etc/opensynaptic.json` |

---

## 异常

| 异常 | 原因 |
|------|------|
| `RuntimeError` | 未设置设备 ID 或核心加载失败 |
| `ValueError` | 配置验证失败或参数类型错误 |
| `OSError` | 文件系统访问错误 |

---

## CMD 字节常数（`CMD` 类）

| 常数 | 值 | 说明 |
|------|------|------|
| `DATA_FULL` | 0x3F | 完整有效负载（模板 + 数据） |
| `DATA_FULL_SEC` | 0x40 | 完整有效负载，XOR 加密 |
| `DATA_DIFF` | 0xAA | 差异更新（仅更改的槽） |
| `DATA_DIFF_SEC` | 0xAB | 差异，XOR 加密 |
| `DATA_HEART` | 0x7F | 心跳（无值变化） |
| `DATA_HEART_SEC` | 0x80 | 心跳，XOR 加密 |
| `ID_REQUEST` | 0x01 | 节点请求设备 ID |
| `ID_ASSIGN` | 0x02 | 服务器分配设备 ID |
| `ID_POOL_REQ` | 0x03 | 节点请求一批 ID |
| `ID_POOL_RES` | 0x04 | 服务器批量 ID 分配 |
| `HANDSHAKE_ACK` | 0x05 | 正向确认 |
| `HANDSHAKE_NACK` | 0x06 | 反向确认 |
| `PING` | 0x09 | 活跃性探测 |
| `PONG` | 0x0A | 活跃性回复 |
| `TIME_REQUEST` | 0x0B | 节点请求服务器时间戳 |
| `TIME_RESPONSE` | 0x0C | 服务器返回 UNIX 时间戳 |
| `SECURE_DICT_READY` | 0x0D | 服务器确认密钥交换 |
| `SECURE_CHANNEL_ACK` | 0x0E | 节点确认加密通道 |

### 策略方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `get_strategy(src_aid, has_template)` | `str` | 返回 `"FULL_PACKET"` 或 `"DIFF_PACKET"` |
| `commit_success(src_aid)` | `None` | 增加成功发送计数器 |
| `commit_failure(src_aid)` | `None` | 增加失败发送计数器 |
| `session_handshake_ack(src_aid, remote_addr)` | `dict` | 开始握手、返回初始化数据 |
| `session_handshake_nack(src_aid, reason)` | `None` | 拒绝握手请求 |
| `control_packet_from_cmd(cmd_byte, payload)` | `bytes` | 从 CMD 字节和有效负载构造完整数据包 |
| `control_packet_to_cmd(packet_bytes)` | `tuple(bytes, bytes)` | 解析数据包为（CMD 字节，有效负载） |
| `session_close(src_aid)` | `None` | 终止设备会话 |

---

## 更多信息

- [CORE_API.md](CORE_API.md) - 核心加载和选择
- [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md) - 配置参考
- [/ARCHITECTURE.md](ARCHITECTURE.md) - 完整架构

---

**语言**: [English](../API.md) | [中文](API.md)  
**最后更新**: 2026-04-04
