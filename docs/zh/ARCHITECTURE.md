---
layout: default
title: OpenSynaptic 系统架构
language: zh
---

# OpenSynaptic 系统架构

**语言**: [English (英文)](../ARCHITECTURE.md) | [中文](ARCHITECTURE.md)  
**最后更新**: 2026-04-04

> **注意**: 这是 [英文版ARCHITECTURE.md](../ARCHITECTURE.md) 的中文翻译总结。关于详细的架构分析，请参考英文原文。

---

## 概述 - Overview

OpenSynaptic 是一个 **2-N-2 IoT 协议栈**，旨在为传感器数据实现实时融合和高效分发。

### 管道阶段 - Pipeline Stages

```
传感器数据 (Sensor Data)
    ↓
转标准化阶段 (Standardization) - UCUM 单位标准化
    ↓
压缩阶段 (Compression) - Base62 编码
    ↓
融合引擎 (Fusion Engine) - 二进制数据包生成
---

## 核心运行时组件

| 组件 | 文件 | 职责 |
|------|------|------|
| `OpenSynaptic` | `src/opensynaptic/core/pycore/core.py` | 协调启动、ID 检查、管道和分发 |
| `OSHandshakeManager` | `src/opensynaptic/core/pycore/handshake.py` | CMD 分发、ID 协商和时间同步 |
| `TransporterManager` | `src/opensynaptic/core/pycore/transporter_manager.py` | 跨层发现/加载启用的驱动程序 |
| `ServiceManager` | `src/opensynaptic/services/service_manager.py` | 内部服务插件的挂载/加载生命周期 |
| `IDAllocator` | `plugins/id_allocator.py` | 分配和持久化 uint32 ID |

---

## 设备 ID 生命周期

1. 节点启动时 `assigned_id` 缺失或为哨兵值 `4294967295`（`MAX_UINT32`）
2. 节点调用 `ensure_id(server_ip, server_port, device_meta)`
3. 服务器回复 `CMD.ID_ASSIGN`
4. 分配的 ID 被持久化到 `Config.json`
5. 在有效 ID 存在之前，`transmit()` 会抛出 `RuntimeError`

---

## 传输分层（应用层 / 传输层 / 物理层）

OpenSynaptic 在三个明确的层中管理传输：

OpenSynaptic 支持**双后端架构**：

### Pycore (Python 核心)
- **语言**: 纯 Python
- **位置**: `src/opensynaptic/core/pycore/core.py`
- **优点**: 易于开发、跨平台、动态灵活
- **场景**: 开发、测试、低流量

### Rscore (Rust 核心) - 高性能
- **语言**: Rust (通过 FFI 调用)
- **位置**: `src/opensynaptic_rscore/` + `target/rscore/`
- **优点**: 极限性能、内存安全、零成本抽象
- **场景**: 生产环境、高吞吐、延迟敏感

#### 后端选择方式
1. **环境变量**: `OPENSYNAPTIC_CORE=rscore` (优先级最高)
2. **配置文件**: `engine_settings.core_backend` 在 Config.json
3. **默认**: pycore (Rust 如果可用，会被自动检测)

---

## 服务和生命周期 - Services and Lifecycle

### 服务管理器 - Service Manager
- **位置**: `src/opensynaptic/services/service_manager.py`
- **职责**: 管理所有服务和插件的生命周期
- **遵循合约**:
  - `__init__`: 初始化
  - `get_required_config()`: 声明配置需求
  - `auto_load`: 是否自动启动
  - `close()`: 优雅关闭（可选）

### 插件系统 - Plugin System
- **类型**: 传输驱动程序、功能扩展
- **位置**: `plugins/` 目录
- **特性**: 热加载、自动注册、依赖解析

### ID 租赁系统 - ID Lease System
- **目的**: 设备身份管理和分层
- **位置**: `plugins/id_allocator.py`
- **功能**: 
  - 为新设备自动分配唯一 ID
  - 支持 ID 分层和命名空间
  - 防止 ID 冲突

---

## 数据流示例 - Data Flow Example

### 完整流程 - Full Pipeline

```
1. 传感器数据输入
   温度: 25.5°C → UCUM 标准: 298.65 K

2. 标准化
   OpenSynapticStandardizer.standardize()
   → {"temperature": 298.65}

3. 压缩
   OpenSynapticEngine.compress()
   → Base62: "3k7x"

4. 融合
   OSVisualFusionEngine.run_engine()
   → 二进制包: 0x[HEADER][TYPE][DATA]
   
   假设值未变化，选择 DIFF 模式 (节省带宽)

5. 分发
   OpenSynaptic.dispatch()
   → UDP: 192.168.1.100:8080
   → MQTT: broker.example.com/sensor/temp
   → UART: COM3 (并行)
```

---

## 配置和自定义 - Configuration and Customization

### 核心配置 - Engine Settings
```json
{
  "engine_settings": {
    "core_backend": "pycore",
    "compression_ratio": 0.85,
    "fusion_mode": "auto"
  }
}
```

### 传输配置 - Transport Configuration
```json
{
  "transporters": {
    "udp": {
      "enabled": true,
      "host": "127.0.0.1",
      "port": 8080
    },
    "mqtt": {
      "enabled": true,
      "broker": "mqtt.example.com"
    }
  }
}
```

详见 [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md)。

---

## 文件树 - File Structure

```
opensynaptic/
├── core/                     # 核心引擎
│   ├── __init__.py
│   ├── coremanager.py        # 核心选择逻辑
│   ├── fusion_engine.py      # 融合引擎
│   ├── compression.py        # 压缩模块
│   ├── standardizer.py       # 标准化模块
│   ├── pycore/
│   │   └── core.py           # Python 核心实现
│   ├── transport_layer/      # 传输协议
│   │   └── protocols/
│   └── physical_layer/       # 物理层
│       └── protocols/
├── services/                 # 服务和驱动
│   ├── service_manager.py    # 生命周期管理
│   └── transporters/
│       └── drivers/          # 传输驱动程序
└── utils/                    # 工具库
    ├── logger.py             # 日志系统
    ├── i18n.py               # 多语言支持
    └── constants.py          # 常量和消息

plugins/
├── id_allocator.py           # ID 租赁系统
└── [user_plugins]            # 定制插件

libraries/
├── Units/                    # UCUM 单位定义
├── OS_Symbols.json           # 符号表
└── harvester.py              # 符号收集工具
```

---

## 关键架构特性 - Key Architecture Features

### 1. 可插拔传输
- 轻松添加新传输驱动程序，无需修改核心
- 多传输并行运行，独立配置和控制

### 2. 灵活的后端选择
- 运行时切换 Python/Rust 核心
- 同一二进制包支持两种后端

### 3. 分层国际化 (i18n)
- 应用消息透明翻译
- 支持动态语言切换
- 在 Python 和 Web 界面中工作

### 4. 高效的数据编码
- Base62 压缩减少带宽 ~40%
- FULL/DIFF 模式优化灵活性
- 字段级别的细粒度控制

### 5. 服务生命周期管理
- 统一的服务初始化、配置和关闭流程
- 优雅的资源清理

---

## 扩展点 - Extension Points

### 添加新传输
1. 在 `src/opensynaptic/services/transporters/drivers/` 创建驱动程序
2. 实现 `BaseTransporter` 接口
3. 在 Config.json 中注册
4. 详见 [TRANSPORTER_PLUGIN.md](TRANSPORTER_PLUGIN.md)

### 添加新功能
1. 在 `plugins/` 中创建插件
2. 遵循 `ServiceManager` 生命周期合约
3. 声明配置需求和依赖
4. 详见 [PLUGIN_DEVELOPMENT_SPECIFICATION_2026.md](../plugins/PLUGIN_DEVELOPMENT_SPECIFICATION_2026.md)

### 添加新后端
1. 在 `opensynaptic_rscore/` 中实现 Rust 核心
2. 导出 FFI 接口
3. 在 `coremanager.py` 中注册选择逻辑
4. 详见 [RSCORE_API.md](RSCORE_API.md)

---

## 性能和优化 - Performance and Optimization

| 指标 | Pycore | Rscore |
|------|--------|--------|
| 吞吐量 (pps) | 10K | 100K+ |
| 延迟 (ms) | 5-10 | 0.1-1 |
| 内存 | 50MB | 10-20MB |
| 启动时间 | 100ms | 50ms |

详见 `data/benchmarks/` 成的基准报告。

---

## 下一步 - Next Steps

- [API.md](API.md) - 了解公共 API
- [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md) - 配置详解
- [PLUGIN_DEVELOPMENT_SPECIFICATION_2026.md](../plugins/PLUGIN_DEVELOPMENT_SPECIFICATION_2026.md) - 插件开发
- [TRANSPORTER_PLUGIN.md](TRANSPORTER_PLUGIN.md) - 创建自定义传输

---

**语言**: [English (英文)](../ARCHITECTURE.md) | [中文](ARCHITECTURE.md)  
**最后更新**: 2026-04-04
