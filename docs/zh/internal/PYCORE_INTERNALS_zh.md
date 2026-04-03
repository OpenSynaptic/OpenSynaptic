---
title: PyCore 内部 API 参考
language: zh
---

# PyCore 内部 API 参考

深度 API 参考，涵盖 `src/opensynaptic/core/pycore/` 中的所有类、方法和数据契约。  
本文档是定义 Rust 版本 rscore API 的主要来源。

---

## 目录

1. [管道概述](#1-管道概述)
2. [数据契约](#2-数据契约)
3. [OpenSynapticStandardizer](#3-opensynapticstandardizer)
4. [OpenSynapticEngine](#4-opensynapticengine)
5. [OSVisualFusionEngine](#5-osvisualfusionengine)
6. [OSHandshakeManager / CMD](#6-oshandshakemanager--cmd)
7. [OpenSynaptic (协调器)](#7-opensynaptic-协调器)
8. [TransporterManager](#8-transportermanager)
9. [安全原语](#9-安全原语)
10. [缓冲区实用工具](#10-缓冲区实用工具)
11. [错误处理约定](#11-错误处理约定)
12. [线程安全协议](#12-线程安全协议)

---

## 1. 管道概述

```
sensors: list[list]
    │
    ▼
OpenSynapticStandardizer.standardize()
    │   输入:  [[传感器_id, 状态, 浮点值, 单位_str], ...]
    │   输出: SensorFact (字典)
    │
    ▼
OpenSynapticEngine.compress()
    │   输入:  SensorFact
    │   输出: compressed_str  (Base62 + URL安全 Base64 文本)
    │
    ▼  raw_input_str = f"{assigned_id};{compressed_str}"
    │
    ▼
OSVisualFusionEngine.run_engine()
    │   输入:  raw_input_str, 策略 ∈ {"FULL","DIFF"}
    │   输出: BinaryFrame (字节)
    │
    ▼
transporter.send(binary_frame, config)
    │   medium ∈ {"UDP","TCP","UART","RS485","CAN","LoRa","MQTT",...}
    └─► 线路
```

**接收路径（镜像）：**

```
线路字节
    │
    ▼
OSVisualFusionEngine.decompress()   或
OSHandshakeManager.classify_and_dispatch()
    │   输出: 解码的 SensorFact 字典  或  HandshakeResult
```

---

## 2. 数据契约

### 2.1 SensorFact（标准化器的输入/输出）

所有键都使用 `s{n}_` 前缀表示传感器插槽（n 从 1 开始）。

```python
{
    "id":    str,          # 设备标识符
    "s":     str,          # 设备状态字符串  ("ONLINE", "OFFLINE", …)
    "t":     int,          # UNIX 时间戳（秒）

    # 各传感器字段（n = 1, 2, 3, …）
    "s1_id": str,          # 传感器 ID
    "s1_s":  str,          # 传感器状态字符串
    "s1_v":  float | int,  # 标准化值（SI 基本单位）
    "s1_u":  str,          # 物理属性字符串（"Pressure"、"Temperature"、…）
                           # 复合：  "Length/Time"（分子/分母）

    # 可选额外字段（来自传递给 standardize() 的 **kwargs）
    "geohash": str,        # 地理位置哈希
    "url":     str,        # 资源 URL
    "msg":     str,        # 补充信息
}
```

### 2.2 CompressedString 格式

```
{device_id}.{state_symbol}.{ts_b64url}|{sensor_segments}{extra_segments}
```

- **ts_b64url** – 6 字节大端字序毫秒 UNIX 时间戳，URL 安全 Base64，无填充
- **sensor_segment** – `{sensor_id}>{state_sym}.{unit_token}:{value_b62}|`
- **unit_token** – 压缩单位（见 §4.2）；`Z` 表示未知
- **extra_segments** – `&{geohash}|`、`#{url_b64}|`、`@{msg_b64}`

### 2.3 BinaryFrame 布局

```
偏移量  大小      字段
──────  ────      ─────────────────────────────────────────────────────
0       1 字节    CMD 字节
1       1 字节    route_count  (N)
2       N×4       路由 ID（每个大端序 uint32；最后一个 = 源 AID）
2+N×4   1 字节    模板 ID（TID，十进制零填充-2，存储为 uint8）
3+N×4   6 字节    时间戳（大端序 uint64 字节 [2..8]，即 6 个最低有效字节）
9+N×4   L 字节    正文（CMD 相关；可能为 XOR 加密）
9+N×4+L 1 字节    CRC-8（多项式=0x07，初值=0x00）覆盖正文
10+N×4+L 2 字节  CRC-16/CCITT（多项式=0x1021，初值=0xFFFF）覆盖整个帧（除最后 2 字节）
```

对于单跳数据包（N=1）:

```
[CMD:1][1:1][AID:4][TID:1][TS:6][BODY:L][CRC8:1][CRC16:2]  总计 = 15+L 字节
```

### 2.4 CMD 字节值

| 常数           | 值   | 方向      | 描述                          |
|----------------|------|-----------|-------------------------------|
| `DATA_FULL`        | 0x3F  | 节点→服务器 | 完整有效负载（模板 + 数据）     |
| `DATA_FULL_SEC`    | 0x40  | 节点→服务器 | 完整有效负载，XOR 加密         |
| `DATA_DIFF`        | 0xAA  | 节点→服务器 | 差分更新（改变的插槽）         |
| `DATA_DIFF_SEC`    | 0xAB  | 节点→服务器 | 差分，XOR 加密                 |
| `DATA_HEART`       | 0x7F  | 节点→服务器 | 心跳（无值更改）               |
| `DATA_HEART_SEC`   | 0x80  | 节点→服务器 | 心跳，XOR 加密                 |
| `ID_REQUEST`       | 0x01  | 节点→服务器 | 请求设备 ID                    |
| `ID_ASSIGN`        | 0x02  | 服务器→节点 | 分配设备 ID                    |
| `ID_POOL_REQ`      | 0x03  | 节点→服务器 | 请求一批 ID                    |
| `ID_POOL_RES`      | 0x04  | 服务器→节点 | 批量 ID 分配                   |
| `HANDSHAKE_ACK`    | 0x05  | 双向        | 正确确认                      |
| `HANDSHAKE_NACK`   | 0x06  | 双向        | 否定确认                      |
| `PING`             | 0x09  | 双向        | 生活性探针                    |
| `PONG`             | 0x0A  | 双向        | 生活性回复                    |
| `TIME_REQUEST`     | 0x0B  | 节点→服务器 | 请求服务器时间戳               |
| `TIME_RESPONSE`    | 0x0C  | 服务器→节点 | 服务器时间戳有效负载            |
| `SECURE_DICT_READY`| 0x0D  | 服务器→节点 | 会话密钥交换确认               |
| `SECURE_CHANNEL_ACK`|0x0E  | 节点→服务器 | 加密通道已确认                 |

**CMD 分类助手**（在 `CMD` 类上）：

```python
CMD.DATA_CMDS        # {0x3F, 0x40, 0xAA, 0xAB, 0x7F, 0x80}
CMD.PLAIN_DATA_CMDS  # {0x3F, 0xAA, 0x7F}
CMD.SECURE_DATA_CMDS # {0x40, 0xAB, 0x80}
CMD.CTRL_CMDS        # 所有握手/ID/时间 CMD
CMD.BASE_DATA_CMD    # 字典：安全→明文映射
CMD.SECURE_DATA_CMD  # 字典：明文→安全映射
```

### 2.5 HandshakeResult

`classify_and_dispatch()` 和所有 `_handle_*` 方法的返回值：

```python
{
    "type":     str,   # "DATA" | "CTRL" | "UNKNOWN" | "ERROR"
    "cmd":      int,   # 原始 CMD 字节
    "result":   dict,  # 解码有效负载或错误字典
    "response": bytes | None,  # 可选回复数据包
}
```

### 2.6 SecureSession（内部字典）

```python
{
    "last":               int,           # 最后一次看到的 UNIX 时间戳
    "peer_addr":          str | None,    # 字符串化（ip、port）元组
    "first_plaintext_ts": int | None,    # 第一个明文数据包的时间戳
    "pending_timestamp":  int | None,    # 候选密钥派生时间戳
    "pending_key":        bytes | None,  # 32 字节会话密钥候选
    "pending_key_hex":    str | None,
    "key":                bytes | None,  # 已确认 32 字节 XOR 会话密钥
    "key_hex":            str | None,
    "dict_ready":         bool,          # 密钥交换完成
    "decrypt_confirmed":  bool,          # 第一次成功解密完成
    "state": str,  # "INIT" | "PLAINTEXT_SENT" | "DICT_READY" | "SECURE"
}
```

---

## 3. OpenSynapticStandardizer

**文件：** `standardization.py`  
**职责：** 将原始传感器读数转换为标准化（SI 基本单位）`SensorFact` 字典。

### 3.1 构造函数

```python
OpenSynapticStandardizer(config_path: str = 'Config.json')
```

| 初始化步骤 | 详情 |
|---|---|
| 加载 `Config.json` | 读取 `engine_settings`、`payload_switches`、`RESOURCES.root` |
| 定位 `libraries/Units/` | 遍历 `RESOURCES.root` → `libraries/` → 回退到 `BASE_DIR/OS_Library` |
| 加载 `Prefixes.json` | 构建 `self.prefixes` 字典和 `self.sorted_prefixes`（按最长优先排序） |
| 加载磁盘缓存 | 读取 `cache/standardization_cache.json` → `self.registry` |

**关键实例属性：**

| 属性 | 类型 | 描述 |
|---|---|---|
| `config` | `dict` | 加载的 `Config.json` |
| `precision` | `int` | 标准化值的小数精度 |
| `switches` | `dict` | 来自配置的 `payload_switches` 部分 |
| `prefixes` | `dict[str, dict]` | SI 前缀定义（十进制 + 二进制） |
| `sorted_prefixes` | `list[str]` | 按长度排序的前缀键（最长优先贪心匹配） |
| `registry` | `dict` | 已解决单位法则的内存缓存 |
| `lib_units_dir` | `str` | `Units/` JSON 库目录的绝对路径 |

本文档的其余部分对应了所有主要类和方法——详见英文原文的数据契约部分和架构说明。

---

有关完整的 API 定义、错误处理协议、线程安全保证和示例代码，请参考 [英文原始文档](../PYCORE_INTERNALS.md)。

本翻译保持了所有代码示例、表格结构和技术术语的完整性，仅在文本说明部分进行了中文本地化。
