---
title: OpenSynaptic – AI 代理指南
language: zh
---

# OpenSynaptic – AI 代理指南

## 项目概述
OpenSynaptic 是一个**2-N-2 高性能 IoT 协议栈**（描述见 `pyproject.toml`）。  
它将传感器读数标准化为 UCUM 单位，通过 Base62 编码进行压缩，将其包装在二进制数据包中，并通过可插拔的传输器进行分派（TCP/UDP/UART/LoRa/MQTT/CAN…）。

---

## 架构：核心管道

```
传感器列表
    → OpenSynapticStandardizer.standardize()   # UCUM 标准化
    → OpenSynapticEngine.compress()            # Base62 固体压缩
    → OSVisualFusionEngine.run_engine()        # 二进制数据包（FULL / DIFF 策略）
    → OpenSynaptic.dispatch(medium="UDP")      # 通过传输器物理发送
```

**关键类和文件：**

| 类 | 文件 | 角色 |
|---|---|---|
| `OpenSynaptic` | `src/opensynaptic/core/pycore/core.py` | 协调器 – 组合所有子系统 |
| `CoreManager` | `src/opensynaptic/core/coremanager.py` | 发现/延迟加载核心插件（`pycore` / `rscore`）并解析外观符号 |
| `OpenSynapticStandardizer` | `src/opensynaptic/core/pycore/standardization.py` | 传感器 → UCUM 事实标准化 |
| `OpenSynapticEngine` | `src/opensynaptic/core/pycore/solidity.py` | Base62 压缩 / 解压 |
| `OSVisualFusionEngine` | `src/opensynaptic/core/pycore/unified_parser.py` | 二进制数据包编码/解码、模板学习 |
| `OSHandshakeManager` | `src/opensynaptic/core/pycore/handshake.py` | CMD 字节分派；设备 ID 协商 |
| `IDAllocator` | `plugins/id_allocator.py` | uint32 ID 池，具有自适应租约策略，持久化到 `data/id_allocation.json` |
| `TransporterManager` | `src/opensynaptic/core/pycore/transporter_manager.py` | 自动发现和延迟加载传输器 |
| `ServiceManager` | `src/opensynaptic/services/service_manager.py` | 进行挂载/加载生命周期中心，用于内部服务和插件 |
| `plugin_registry` 助手 | `src/opensynaptic/services/plugin_registry.py` | 内置插件默认值 + 别名标准化（`web-user` → `web_user`） |

---

## Config.json – 单一事实来源

项目根目录的 `Config.json` 仍然是默认值和回购本地工具的模板/SSOT。  
运行时 CLI/节点会话默认为用户配置 `~/.config/opensynaptic/Config.json`（`get_user_config_path()`），并在需要时从项目 `Config.json` 引导/迁移。
`OSContext`（`utils/paths.py`）仍然通过从 `__file__` 向上遍历直到找到项目 `Config.json` 来自动检测回购根目录。

关键键：
- `assigned_id` – uint32 设备 ID；`4294967295`（MAX_UINT32）是**"未分配"的哨兵**
- `--config` 在 CLI / `OpenSynaptic()` 构造函数中省略 – 默认为 `~/.config/opensynaptic/Config.json`
- `security_settings.id_lease` – ID 重用/租赁策略对象（请参见下文了解子键）
  - `offline_hold_days` – 默认保留期（转换为 `base_lease_seconds`）
  - `base_lease_seconds` – 新分配或重新触及的 ID 的基础租赁期（默认 2,592,000 = 30 天）
  - `min_lease_seconds` – 最小租赁下限（默认 0，表示自适应可降至零）
  - `rate_window_seconds` – 新设备速率计算的观察窗口（默认 3600）
  - `high_rate_threshold_per_hour` – 触发自适应缩短的阈值（默认 60/小时）
  - `ultra_rate_threshold_per_hour` – 触发强制零租赁的阈值（默认 180/小时）
  - `ultra_rate_sustain_seconds` – 在应用强制零租赁前，超高速率必须持续的时间（默认 600 秒）
  - `high_rate_min_factor` – 检测到高速率时应用的乘数（默认 0.2，基础租赁的最小 20%）
  - `adaptive_enabled` – 启用/禁用自适应租赁缩短（默认 `true`）
  - `ultra_force_release` – 超高速率活跃时立即过期离线 ID（默认 `true`）
  - `metrics_emit_interval_seconds` – 发出租赁指标的频率（默认 5 秒）
- `RESOURCES.transporters_status` – CLI/工具使用的遗留合并状态映射；保持小写键
- `RESOURCES.application_status / transport_status / physical_status` – L7/L4/PHY 加载的活跃启用映射
- `RESOURCES.application_config / transport_config / physical_config` – 传递给 `send()` 的每层驱动程序选项作为 `application_options` / `transport_options` / `physical_options`
- `RESOURCES.registry` – 设备注册表目录的路径（默认 `data/device_registry/`）
- `engine_settings.precision` – Base62 十进制精度（默认 4）
- `engine_settings.core_backend` – 活跃核心插件（`pycore` / `rscore`），支持 `OPENSYNAPTIC_CORE` 环境变量覆盖
- `engine_settings.active_standardization / active_compression / active_collapse` – 管道阶段切换
- `engine_settings.zero_copy_transport` – 启用 memoryview 直通发送路径（默认 `true`；设为 `false` 以使用遗留字节物化回退）
- `RESOURCES.service_plugins.<plugin_name>` – 扩展的插件默认值，包括 `tui`、`web_user`、`dependency_manager`、`env_guard`

---

## ID 生命周期与租赁管理

**基本流程：**
1. 新设备从 `assigned_id` 缺失或 `4294967295`（未分配哨兵）开始。
2. 调用 `node.ensure_id(server_ip, server_port, device_meta)` – 通过 UDP 发送 `CMD.ID_REQUEST (0x01)`。
3. 服务器通过 `IDAllocator.allocate_id(meta)` 响应 `CMD.ID_ASSIGN (0x02)`。
4. 设备在 `Config.json` 中记录 `assigned_id`；没有有效 ID 则 `transmit()` 引发 `RuntimeError`。

**ID 租赁与重用策略：**
- 检测到设备离线 → ID 标记为 `offline` 状态，租赁倒计时开始（`lease_expires_at = now + effective_lease_seconds`）
- 默认租赁：**30 天**（可配置 `security_settings.id_lease.offline_hold_days`）
- 当设备使用相同的稳定密钥（MAC/序列号/UUID）重新连接时 → ID 重新激活，租赁重置为基础
- 过期的 ID 会自动回收，移至 `released` 池供新设备重用
- **新设备速率自适应控制**：
  - 高速率（> `high_rate_threshold_per_hour`，默认 60/小时）→ 租赁按因子 `high_rate_min_factor`（默认 0.2）缩短
  - 超高速率（> `ultra_rate_threshold_per_hour`，默认 180/小时，持续 `ultra_rate_sustain_seconds`，默认 600 秒）→ `force_zero_lease_active=true`，离线 ID 立即过期
- `security_settings.id_lease` 中的配置键驱动所有租赁逻辑；`IDAllocator` 在 `__init__` 和每次分配时读取它们
- 指标（`new_device_rate_per_hour`、`effective_lease_seconds`、`ultra_rate_active`）每 `metrics_emit_interval_seconds`（默认 5 秒）发布到可选的 `metrics_sink` 可调用对象；租赁指标也每 `metrics_flush_seconds`（默认 10 秒）刷新到 `Config.json`

**文档**：详见 `docs/ID_LEASE_SYSTEM.md` 的综合指南和 `docs/ID_LEASE_CONFIG_REFERENCE.md` 的配置快速入门。

---

## 传输器插件系统

传输器分三层分布，每层使用 `LayeredProtocolManager`：

- **应用（L7）**：`src/opensynaptic/services/transporters/drivers/` → 由 `TransporterService` 管理
  - 自动发现限制为 `TransporterService.APP_LAYER_DRIVERS`（目前为 `{'mqtt', 'matter', 'zigbee'}`）
  - 添加新应用驱动程序：添加键到 `APP_LAYER_DRIVERS`，创建驱动程序模块，在 `application_status` 中启用 + 在 `application_config` 中配置
- **传输（L4）**：`src/opensynaptic/core/transport_layer/protocols/` → 由 `TransportLayerManager` 管理
  - 候选项：`udp`、`tcp`、`quic`、`iwip`、`uip`（`manager.py:_CANDIDATES` 中的元组）
- **物理（PHY）**：`src/opensynaptic/core/physical_layer/protocols/` → 由 `PhysicalLayerManager` 管理
  - 候选项：`uart`、`rs485`、`can`、`lora`、`bluetooth`（`manager.py:_CANDIDATES` 中的元组）

**常见模式：**
- 所有驱动程序实现 `send(payload: bytes, config: dict) -> bool`（可选 `listen(config, callback)`）
- 通过**层特定的**状态映射启用/禁用：`application_status`、`transport_status`、`physical_status`
- 每层配置在 `application_config`、`transport_config`、`physical_config` 中
- 添加新的 T/L4/PHY 协议：更新层 `manager.py:_CANDIDATES` 元组，更新 `TransporterManager` 协议集合（由 `_migrate_resource_maps()` 使用），然后在 `Config.json` 中添加状态/配置条目
- 所有传输器键必须在状态/配置映射中**小写**；`TransporterManager._migrate_resource_maps()` 保持遗留 `transporters_status` 作为合并镜像

---

## 设备注册表分片

注册表文件位于：
```
data/device_registry/{id[0:2]}/{id[2:4]}/{aid}.json
```
其中分片段是从 `str(aid).zfill(10)` 派生的。  
助手：`from opensynaptic.utils import get_registry_path; get_registry_path(aid)`

---

## 性能指标与监控

**尾部延迟百分位数（test_plugin）：**
- `avg_latency_ms` – 所有数据包的平均延迟
- `p95_latency_ms` – 95 百分位数延迟
- `p99_latency_ms` – 99 百分位数延迟（关键 SLA 指标）
- `p99_9_latency_ms` – 99.9 百分位数延迟
- `p99_99_latency_ms` – 99.99 百分位数延迟（极端尾部）
- `min_latency_ms`、`max_latency_ms` – 端点延迟

所有延迟字段由 `src/opensynaptic/services/test_plugin/stress_tests.py` 计算和汇总，并通过 `--suite stress` 和 `--suite compare` 运行在 CLI 输出中可用。

**ID 租赁指标：**
- `new_device_rate_per_hour` – 新设备分配的滚动速率；驱动自适应租赁缩短
- `effective_lease_seconds` – 应用自适应策略后的计算租赁期
- `ultra_rate_active` – 布尔标志，指示是否持续超过超高速率阈值
- `force_zero_lease_active` – 布尔标志，指示离线 ID 是否被强制过期
- `total_reclaimed` – 从过期租赁回收的 ID 的累计计数
- 由 `IDAllocator._emit_metrics_nolock()` 每 `metrics_emit_interval_seconds`（默认 5 秒）发布到可选 `metrics_sink` 可调用对象；租赁指标也每 `metrics_flush_seconds`（默认 10 秒）刷新到 `Config.json`

---

## 单位库

- `libraries/Units/` – 作为 JSON 的 UCUM 单位定义，带有 `__METADATA__.OS_UNIT_SYMBOLS`。
- `libraries/harvester.py → SymbolHarvester.sync()` – 将所有单位文件合并到 `libraries/OS_Symbols.json` 中。
- `OpenSynapticEngine` 从 `Config.json` 中的 `RESOURCES.prefixes` 或 `RESOURCES.symbols` 解析其符号表；保持该路径与收获器输出一致。
- **添加/编辑任何单位 JSON 后运行收获器**，以便 `OpenSynapticEngine` 拿起新符号。

---

## 日志约定

使用 `os_log` 单例（`from opensynaptic.utils import os_log`）：

```python
os_log.err("MODULE_ID", "EVENT_ID", exception, {"context": "dict"})
os_log.info("STD", "UNIT", "解决的 kg", {"原始": "kilogram"})
os_log.log_with_const("info", LogMsg.READY, root=self.base_dir)
```

所有面向用户的消息模板都在 `utils/constants.py:MESSAGES` 中。  
在将它们与 `log_with_const` 一起使用之前，在那里添加新的 `LogMsg` 枚举成员。
- 接收器运行时性能统计通过 `src/opensynaptic/core/Receiver.py` 中的 `ReceiverRuntime(report_interval_s=60.0)` 默认以**60 秒**报告节奏（需要更短调试节奏时显式覆盖 `report_interval_s`）。

---

## 开发工作流

**安装（可编辑）：**
```bash
pip install -e .
```

**运行独立集成烟雾线束**（回购本地快速验证）：
```bash
python scripts/integration_test.py
```

**运行协议接收线束**（默认 UDP；支持通过 `--protocol tcp` 的 TCP）：
```bash
python scripts/udp_receive_test.py --protocol udp --host 127.0.0.1 --port 8080 --config Config.json
```

**运行内置插件测试套件：**
```bash
python -u src/main.py plugin-test --suite component
python -u src/main.py plugin-test --suite stress --workers 8 --total 200
python -u src/main.py plugin-test --suite all --workers 8 --total 200
python -u src/main.py plugin-test --suite full_load --total 100000 --with-component
python -u src/main.py plugin-test --suite integration
python -u src/main.py plugin-test --suite audit
```

**使用单标志测试配置文件（映射到压力/比较预设）：**
```bash
python -u src/main.py plugin-test --profile quick
python -u src/main.py plugin-test --profile deep
python -u src/main.py plugin-test --profile record
```

**运行后端比较 / 高负载分析流：**
```bash
python -u src/main.py plugin-test --suite compare --total 10000 --workers 8 --processes 2 --threads-per-process 4 --runs 2 --warmup 1
python -u src/main.py plugin-test --suite stress --auto-profile --profile-total 50000 --profile-runs 1 --final-runs 1 --profile-processes 1,2,4,8 --profile-threads 4,8,16 --profile-batches 32,64,128
```

**切换 Rust 核心后端：**
```bash
python -u src/main.py core --set rscore --persist
```

**构建 Rust 核心（CLI）：**
```bash
python -u src/main.py rscore-build
python -u src/main.py rscore-check
```

---

**注：** 本翻译保持了所有代码示例、配置键和命令的完整性。有关最新的项目信息，请参考英文原始 AGENTS.md。
