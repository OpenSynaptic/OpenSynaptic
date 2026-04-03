---
layout: default
title: Config.json 架构参考
language: zh
---

# Config.json 架构参考

**语言**: [English](../CONFIG_SCHEMA.md) | [中文](CONFIG_SCHEMA.md)

`Config.json` 位于项目根目录，是**所有运行时行为的单一信息源**。  
`OSContext` 通过从 `__file__` 向上遍历直到找到文件来自动检测它。

---

## 顶级键

| 键 | 类型 | 默认值 | 描述 |
|---|---|---|---|
| `VERSION` | `string` | `"1.0.0"` | 协议版本字符串 |
| `assigned_id` | `uint32` | `4294967295` | 设备 ID。`4294967295`（MAX_UINT32）是*未分配*的哨兵。永远不要将其用作真实 ID。 |
| `device_id` | `string` | `"UNKNOWN"` | 传感器有效负载中使用的人类可读节点标识符 |

---

## `OpenSynaptic_Setting`

高级功能开关。

```json
"OpenSynaptic_Setting": {
    "Server_Core": true,
    "Node_Core":   true,
    "Client_Core": true
}
```

| 键 | 类型 | 默认值 | 效果 |
|---|---|---|---|
| `Server_Core` | bool | `true` | 启用服务器端 ID 分配和数据包接收 |
| `Node_Core` | bool | `true` | 启用节点模式（数据生成 + 传输） |
| `Client_Core` | bool | `true` | 启用客户端握手 / ID 请求 |
| `default_medium` | string | `"UDP"` | 当未指定介质时由 `dispatch()` 使用的回退传输介质 |

---

## `Server_Core`

内置 UDP 服务器的配置。

```json
"Server_Core": {
    "port":     8080,
    "host":     "0.0.0.0",
    "Start_ID": 1,
    "End_ID":   4294967294
}
```

| 键 | 类型 | 默认值 | 描述 |
|---|---|---|---|
| `port` | int | `8080` | UDP 监听端口 |
| `host` | string | `"0.0.0.0"` | 绑定地址 |
| `Start_ID` | int | `1` | 可分配池中的第一个 ID |
| `End_ID` | int | `4294967294` | 可分配池中的最后一个 ID |

---

## `Client_Core`

客户端握手的服务器端点。

```json
"Client_Core": {
    "server_host": "localhost",
    "server_port": 8080
}
```

---

## `Node_Core`

节点身份和子池配置。

```json
"Node_Core": {
    "node_id":     "",
    "template_id": "",
    "pool":        0,
    "Start_ID":    0,
    "End_ID":      0
}
```

---

## `RESOURCES`

所有资源路径、传输器注册表和驱动配置。

```json
"RESOURCES": {
    "root":     "OS_library/opensynaptic_core/",
    "registry": "data/device_registry/",
    "symbols":  "data/symbols.json",
    
    "transporters_status": { "<name>": true|false },
    "service_plugins": {
        "<plugin_name>": {
            "enabled": true,
            "config": {}
        }
    }
}
```

---

## `engine_settings`

引擎行为控制。

```json
"engine_settings": {
    "core_backend": "pycore",
    "precision": 4,
    "active_standardization": true,
    "active_compression": true,
    "fusion_mode": "auto"
}
```

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `core_backend` | string | `"pycore"` | 活跃核心：`"pycore"` 或 `"rscore"` |
| `precision` | int | `4` | Base62 小数位数 |
| `active_standardization` | bool | `true` | 启用 UCUM 标准化阶段 |
| `active_compression` | bool | `true` | 启用 Base62 压缩阶段 |
| `fusion_mode` | string | `"auto"` | 融合策略：`"auto"`、`"full"` 或 `"diff"` |

---

## `security_settings`

安全和数据完整性设置。

```json
"security_settings": {
    "drop_on_crc16_failure": true,
    "enable_xor_encryption": false,
    "session_timeout_seconds": 300
}
```

| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `drop_on_crc16_failure` | bool | `true` | CRC 校验失败时丢弃数据包 |
| `enable_xor_encryption` | bool | `false` | 启用简单 XOR 加密（用于演示） |
| `session_timeout_seconds` | int | `300` | 会话超时（秒） |

---

## `transporters`

传输器配置映射，按类型分组。

```json
"transporters": {
    "udp": {
        "enabled": true,
        "host": "127.0.0.1",
        "port": 8080,
        "timeout": 5.0
    },
    "mqtt": {
        "enabled": false,
        "broker": "mqtt.example.com",
        "port": 1883,
        "topic": "opensynaptic/data"
    },
    "uart": {
        "enabled": false,
        "port": "COM3",
        "baudrate": 115200
    }
| 键 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `drop_on_crc16_failure` | bool | `true` | CRC16 校验失败时丢弃数据包 |
| `enable_xor_encryption` | bool | `false` | 在分发前启用数据包 XOR 加密 |
| `session_timeout_seconds` | int | `300` | 握手会话过期时间（秒） |

---

## `payload_switches`

精细控制每个编码数据包中包含哪些字段。

```json
"payload_switches": {
    "DeviceId":           true,
    "DeviceStatus":       true,
    "Timestamp":          true,
    "SubTemplateId":      true,
    "SensorId":           true,
    "SensorStatus":       true,
    "PhysicalAttribute":  false,
    "NormalizedValue":    true,
    "GeohashId":          false,
    "SupplementaryMessage": true,
    "ResourceUrl":        false
}
```

将字段设置为 `false` 会从每个数据包中省略它，以降低带宽为代价放弃该数据字段。

---

## `storage`

日志记录、SQL 后端和备份配置。

```json
"storage": {
    "directory":         "os_log",
    "registry_sharding": true,
    "sql": {
        "enabled": false,
        "dialect": "sqlite",
        "driver":  { "path": "data/opensynaptic.db" }
    },
    "standard_backup": {
        "enable":   true,
        "filename": "os_log/physics_fact_backup.jsonl"
    },
    "compressed_backup": {
        "enable":   true,
        "filename": "os_log/os_protocol_backup.os"
    }
}
```

| 键 | 类型 | 默认值 | 效果 |
|---|---|---|---|
| `directory` | string | `"os_log"` | 日志输出目录 |
| `registry_sharding` | bool | `true` | 在子目录（`id[0:2]/id[2:4]/`）中分割设备注册表 |
| `sql.enabled` | bool | `false` | 通过 `DatabaseManager` 启用 SQL 导出 |
| `sql.dialect` | string | `"sqlite"` | `"sqlite"`、`"mysql"` 或 `"postgresql"` |
| `sql.driver.path` | string | — | SQLite 文件路径 |
| `standard_backup.enable` | bool | `true` | 将原始事实字典追加到 JSONL 文件 |
| `compressed_backup.enable` | bool | `true` | 将原始二进制数据包追加到 `.os` 文件 |

---

## `automation`

代码生成辅助工具。

```json
"automation": {
    "cpp_header": "os_symbols.hpp"
}
```

| 键 | 类型 | 描述 |
|---|---|---|
| `cpp_header` | string | 由库收集器生成的 C++ 符号头的输出路径 |

---

## 运行时编辑 Config

使用 CLI 命令安全地修改 Config.json，无需手动编辑文件：

```powershell
# 查看一个部分
python -u src/main.py config-show --config Config.json --section engine_settings

# 读取特定键
python -u src/main.py config-get --config Config.json --key engine_settings.precision

# 写入类型化值
python -u src/main.py config-set --config Config.json --key engine_settings.precision --value 6 --type int

# 启用传输器
python -u src/main.py transporter-toggle --config Config.json --name udp --enable
```

---

## 验证

通过以下方式验证 `Config.json`：

```powershell
python -u src/main.py config-show
python -u src/main.py config-get engine_settings.core_backend
python -u src/main.py config-set engine_settings.precision 3
```

---

**语言**: [English](../CONFIG_SCHEMA.md) | [中文](CONFIG_SCHEMA.md)  
**最后更新**: 2026-04-04
