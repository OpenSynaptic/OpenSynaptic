---
layout: default
title: 传输器插件指南
language: zh
---

# 传输器插件指南

如何为 OpenSynaptic 写入、注册和启用新的传输器。

---

## 概览

OpenSynaptic 的传输层分为三个层级：

| 层级 | 配置键 | 驱动程序位置 | 示例 |
|------|--------|-------------|------|
| **应用层** | `RESOURCES.application_status` | `services/transporters/drivers/` | MQTT、Matter、Zigbee |
| **传输层** | `RESOURCES.transport_status` | `core/transport_layer/` | UDP、TCP、QUIC、lwIP、uIP |
| **物理层** | `RESOURCES.physical_status` | `core/physical_layer/` | UART、RS-485、CAN、LoRa、Bluetooth |

发现行为取决于层级：

- **应用层**：受 `TransporterService.APP_LAYER_DRIVERS` 约束。
- **传输层**：受 `TransportLayerManager._CANDIDATES` 约束。
- **物理层**：受 `PhysicalLayerManager._CANDIDATES` 约束。

`ServiceManager` 处理应用层驱动；传输层和物理层由各自专用的层管理器管理。

有效负载物理化由 `opensynaptic.utils.buffer.to_wire_payload()` 集中处理，以保持跨应用/传输/物理发送路径的零复制行为一致。

---

## 必需接口

每个传输器模块必须公开：

```python
def send(payload: bytes, config: dict) -> bool:
    """
    使用此驱动程序实现的任何介质发送 payload。

    参数
    ----------
    payload : bytes   – 预编码的二进制数据包（来自 OSVisualFusionEngine）
    config  : dict    – 合并的节点 Config.json（完整字典）

    返回值
    -------
    bool – 成功返回 True，失败返回 False
    """
    ...
```

### 可选接口

```python
def listen(config: dict, callback) -> None:
    """
    启动阻塞式（或后台线程）接收循环。

    参数
    ----------
    config   : dict       – 完整的节点配置
    callback : callable   – 为每个入站数据包调用（raw_bytes: bytes、addr: tuple）
    """
    ...
```

---

## 逐步说明：添加传输层驱动程序

### 1. 创建驱动程序文件

对于 **传输层** 驱动程序（例如 WebSocket），创建：

```
src/opensynaptic/core/transport_layer/websocket.py
```

至少实现：

```python
# src/opensynaptic/core/transport_layer/websocket.py
import websocket  # pip install websocket-client

def send(payload: bytes, config: dict) -> bool:
    try:
        ws_cfg = config.get('RESOURCES', {}).get('transport_config', {}).get('websocket', {})
        url = ws_cfg.get('url', 'ws://localhost:8765')
        ws = websocket.create_connection(url, timeout=ws_cfg.get('timeout', 3.0))
        ws.send_binary(payload)
        ws.close()
        return True
    except Exception as exc:
        return False
```

### 2. 在管理器候选列表和 Config.json 中注册

将驱动程序键/模块添加到传输层候选元组（`TransportLayerManager._CANDIDATES`），然后确保 `Config.json` 具有状态条目：

```json
"RESOURCES": {
    "transport_status": {
        "websocket": false
    }
}
```

当需要时，在 `RESOURCES.transport_config` 下添加匹配的设置。

### 3. 启用驱动程序

通过 CLI：

```powershell
python -u src/main.py transporter-toggle --config Config.json --name websocket --enable
```

或通过 `config-set`：

```powershell
python -u src/main.py config-set --config Config.json --key RESOURCES.transport_status.websocket --value true --type bool
```

或直接在 `Config.json` 中：

```json
"transport_status": {
    "websocket": true
}
```

### 4. 添加可选配置块

在匹配的配置键下放置驱动程序特定的设置：

```json
"transport_config": {
    "websocket": {
        "url": "ws://192.168.1.100:8765",
        "timeout": 3.0
    }
}
```

在 `send()` 内通过以下方式访问它们：

```python
ws_cfg = config.get('RESOURCES', {}).get('transport_config', {}).get('websocket', {})
```

---

## 逐步说明：添加应用层驱动程序

应用层驱动程序位于 `services/transporters/drivers/` 中，并且必须在 `services/transporters/main.py` 内的 `ServiceManager.APP_LAYER_DRIVERS` 中列出。

### 1. 创建驱动程序文件

```
src/opensynaptic/services/transporters/drivers/myapp.py
```

最小实现：

```python
def send(payload: bytes, config: dict) -> bool:
    app_opts = config.get('application_options', {})
    # ... 发送逻辑 ...
    return True
```

### 2. 在 APP_LAYER_DRIVERS 中注册

在 `services/transporters/main.py` 中：

```python
class TransporterService:
    APP_LAYER_DRIVERS = {'mqtt', 'matter', 'zigbee', 'myapp'}   # ← 在这里添加
```

如果密钥未在此处列出，即使文件存在，应用层驱动程序也不会被加载。

### 3. 在 Config.json 中启用

```json
"application_status": {
    "myapp": true
},
"application_config": {
    "myapp": {
        "endpoint": "https://..."
    }
}
```

---

## 逐步说明：添加物理层驱动程序

物理驱动程序位于 `core/physical_layer/`，遵循相同的 `send()` / `listen()` 约定。  
在 `PhysicalLayerManager._CANDIDATES` 中注册新协议，然后在 `RESOURCES.physical_status` 下启用它们。

示例：添加 `bluetooth.py`：

```
src/opensynaptic/core/physical_layer/protocols/bluetooth.py
```

```json
"physical_status": {
    "bluetooth": true
},
"physical_config": {
    "bluetooth": {
        "address": "AA:BB:CC:DD:EE:FF",
        "port": 1
    }
}
```

---

## 命名约定

- 文件名（小写，无连字符）：`udp.py`、`lora.py`、`my_proto.py`
- Config 中的状态键（相同小写）：`"udp"`、`"lora"`、`"my_proto"`
- `TransporterManager` 在查找前将介质字符串规范化为小写

---

## 测试驱动程序

启用后，通过 CLI 验证：

```powershell
python -u src/main.py transport-status --config Config.json
python -u src/main.py transmit --config Config.json --sensor-id V1 --value 1.0 --unit Pa --medium myapp
```

要分离测试 send / receive，使用 `inject` + 你自己的监听器：

```powershell
python -u src/main.py inject --config Config.json --module full --sensor-id V1 --value 3.14 --unit Pa
```
