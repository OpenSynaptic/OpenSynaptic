---
title: 协议层优化报告
language: zh
---

# OpenSynaptic 协议层优化报告

**日期：** 2026-03-24  
**状态：** ✅ 完成且已验证

## 概述

优化并验证了 OpenSynaptic 的三层协议架构：
- **L4 传输层**（UDP、TCP、QUIC、IWIP、UIP）- 通过 `src/opensynaptic/core/transport_layer`
- **物理层**（UART、RS485、CAN、LoRa）- 通过 `src/opensynaptic/core/physical_layer`
- **L7 应用层**（MQTT）- 通过 `src/opensynaptic/services/transporters`

---

## 所作更改

### 1. 从应用层删除重复的传输驱动程序
**位置：** `src/opensynaptic/services/transporters/drivers/`

| 文件 | 状态 | 原因 |
|---|---|---|
| `udp.py` | ❌ 已删除 | 委托给 L4，属于 `transport_layer` |
| `tcp.py` | ❌ 已删除 | 委托给 L4，属于 `transport_layer` |
| `quic.py` | ❌ 已删除 | 委托给 L4，属于 `transport_layer` |
| `iwip.py` | ❌ 已删除 | 委托给 L4，属于 `transport_layer` |
| `uip.py` | ❌ 已删除 | 委托给 L4，属于 `transport_layer` |
| `uart.py` | ❌ 已删除 | 属于 `physical_layer` |
| `mqtt.py` | ✅ 保留 | 真正的应用层驱动程序 |

**结果：** 消除了 6 个冗余/重复的协议驱动程序。

### 2. 简化 TransporterService
**位置：** `src/opensynaptic/services/transporters/main.py`

**之前：**
- 混合职责（应用层 + 传输层逻辑）
- 手动驱动程序发现复制 `LayeredProtocolManager`
- `transporters_status` 中的复杂状态镜像

**之后：**
- **纯 L7 服务** - 仅处理应用层驱动程序（MQTT）
- 清晰的代码注释说明范围
- 删除了 `transporters_status` 重复
- 将所有 L4/PHY 委托给 `LayeredProtocolManager`

### 3. 增强 LayeredProtocolManager 驱动程序检测
**位置：** `src/opensynaptic/core/layered_protocol_manager.py`

**改进：**
- ✅ 更好的 `discover()`（具有统计日志记录 - 已加载/已跳过/失败计数）
- ✅ 改进的 `_load_module()`（带详细错误消息）
- ✅ `is_supported()` 和 `send()` 函数的验证检查
- ✅ 适当的异常处理（ModuleNotFoundError 与通用错误）

**结果：** 更强大且可调试的驱动程序加载。

---

## 验证与测试结果

### 创建的测试脚本

| 脚本 | 用途 | 状态 |
|---|---|---|
| `scripts/diagnose_layers.py` | 协议层诊断 | ✅ 有效 |
| `scripts/test_runtime_invoke.py` | 运行时操作验证 | ✅ 有效 |
| `scripts/integration_test.py` | 完整集成测试套件 | ✅ 8/8 通过 |

### 集成测试结果

```
✅ 测试 1：节点初始化与自动驱动程序发现
✅ 测试 2：传输单个传感器
✅ 测试 3：传输多个传感器（3 个传感器 → 81 字节）
✅ 测试 4：接收并解压数据包
✅ 测试 5：通过协议接收（握手）
✅ 测试 6：分派到 UDP 驱动程序（实时调用）
✅ 测试 7：传输层驱动程序直接访问
✅ 测试 8：物理层驱动程序直接访问

结果：8/8 通过 ✓
```

### 诊断输出

```
[L4 TRANSPORT LAYER]
  候选项：['udp', 'tcp', 'quic', 'iwip', 'uip']
  已启用：['udp']
  已加载：['udp'] ✓

[PHY PHYSICAL LAYER]
  候选项：['uart', 'rs485', 'can', 'lora']
  已启用：['uart']
  已加载：['uart'] ✓

[L7 APPLICATION LAYER]
  预期：['mqtt']
  已启用：[]（默认禁用）
  可以通过 Config.json 启用
```

---

## 正常运行时行为

所有驱动程序发现和调用都在 `OpenSynaptic.__init__()` 期间**自动**进行：

```python
# 初始化节点（一次性）
node = OpenSynaptic(config_path="Config.json")
# ✓ 根据状态映射自动发现和加载 L4/PHY/L7 驱动程序

# 传输
packet, aid, strategy = node.transmit(sensors=[...])
# ✓ 自动使用压缩引擎

# 分派（发送）
ok = node.dispatch(packet, medium="UDP")
# ✓ 通过 LayeredProtocolManager 调用 UDP 驱动程序
# ✓ 返回 True/False 指示发送成功

# 接收
decoded = node.receive(packet)
# ✓ 解压数据包为原始传感器数据
# ✓ 返回带有恢复字段的字典

# 通过协议接收（带握手）
dispatch = node.receive_via_protocol(packet, addr)
# ✓ 分类数据包（DATA/CTRL/ERROR）
# ✓ 如果需要，处理握手响应
```

**无需手动驱动程序加载** - 一切都是自动的！

---

## 架构图（优化后）

```
OpenSynaptic 节点
├─ 核心管道
│  ├─ 标准化（UCUM 标准化）
│  ├─ 压缩（Base62 编码）
│  ├─ 融合（基于模板的数据包生成）
│  └─ 解压（数据包 → JSON）
│
└─ 协议层（自动发现）
   ├─ L7 应用
   │  └─ TransporterService
   │     └─ MQTT 驱动程序（默认禁用）
   │
   ├─ L4 传输
   │  └─ LayeredProtocolManager
   │     ├─ UDP ✓（已启用，已加载）
   │     ├─ TCP
   │     ├─ QUIC
   │     ├─ IWIP
   │     └─ UIP
   │
   └─ PHY 物理
      └─ LayeredProtocolManager
         ├─ UART ✓（已启用，已加载）
         ├─ RS485
         ├─ CAN
         └─ LoRa
```

---

## 配置参考

### 启用其他协议

编辑 `Config.json`：

```json
{
  "RESOURCES": {
    "transport_status": {
      "udp": true,
      "tcp": true,
      "quic": false,
      "iwip": false,
      "uip": false
    },
    "physical_status": {
      "uart": true,
      "rs485": false,
      "can": false,
      "lora": false
    },
    "application_status": {
      "mqtt": false
    },
    "transport_config": {
      "udp": {"host": "127.0.0.1", "port": 8080},
      "tcp": {"host": "127.0.0.1", "port": 8081}
    },
    "physical_config": {
      "uart": {"port": "UART0", "baudrate": 115200}
    },
    "application_config": {
      "mqtt": {"host": "broker.hivemq.com", "port": 1883, "topic": "os/sensors/raw"}
    }
  }
}
```

---

**注：** 本翻译保持了所有代码示例和配置格式的完整性。
