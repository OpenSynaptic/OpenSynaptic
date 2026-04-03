---
layout: default
title: OpenSynaptic v1.0.0-rc1 发布说明
language: zh
---

# OpenSynaptic v1.0.0-rc1 发布说明

发布日期：2026-03-26  
类型：发布候选版本（打包硬化 + 传输器扩展 + 文档和审计对齐）

---

## 亮点

- 为 Python 和 Rust 分发工作流准备了发布候选包基线。
- 添加了新的应用层网关传输器：Matter 和 Zigbee。
- 添加了新的物理层网关协议：Bluetooth。
- 扩展了驱动程序功能审计以覆盖 Matter、Zigbee 和 Bluetooth。
- 更新了架构和传输器文档以反映新的协议覆盖范围和配置默认值。

---

## 范围摘要

此 RC 专注于发布就绪和协议表面扩展：

- 跨平台交付的打包和发布自动化。
- 运行时传输器矩阵扩展（L7 + PHY）。
- 核心、CLI 和根配置模板之间的配置/默认映射同步。
- 文档和审计工具一致性更新。

此 RC 范围内未引入任何有线格式破坏性变更。

---

## 新增功能

### 打包和发布基础设施

- 添加了根目录 `LICENSE`（MIT）。
- 为矩阵测试/构建任务添加了 CI 工作流 `.github/workflows/ci.yml`。
- 为工件发布管道添加了标签驱动的发布工作流 `.github/workflows/release.yml`。
- 在 `src/opensynaptic/core/rscore/rust/` 下添加了 Rust wheel 打包脚手架：
  - `pyproject.toml`（使用 maturin 构建后端）
  - `README.md`（用于本地构建）
  - 在 `src/lib.rs` 中的 PyO3 模块入口点集成

### 基线测试套件

- 添加了 `tests/unit/test_core_algorithms.py`（CRC/Base62/数据包编码-解码检查）。
- 添加了 `tests/integration/test_pipeline_e2e.py`（端到端虚拟传感器管道往返）。
- 添加了 `tests/README.md`（包含本地测试调用指导）。

### 新传输器/协议

- 添加了应用层驱动程序：`src/opensynaptic/services/transporters/drivers/matter.py`。
- 添加了应用层驱动程序：`src/opensynaptic/services/transporters/drivers/zigbee.py`。
- 添加了物理层协议：`src/opensynaptic/core/physical_layer/protocols/bluetooth.py`。

---

## 修改内容

### 打包元数据和构建配置

- 使用发布级元数据更新了 `pyproject.toml`：
  - 为发布候选版本行设置版本
  - readme/license/requires-python/classifiers/keywords
  - `dev` 和 `rscore` 可选依赖组
  - pytest/coverage 工具部分
- 更新了包数据配置以包括本地源文件：
  - `opensynaptic.utils.base62/*.c`
  - `opensynaptic.utils.security/*.c`

### 传输器发现和默认值

- 更新了 `src/opensynaptic/services/transporters/main.py` 中的应用层驱动程序允许列表：
  - 现在包括 `mqtt`、`matter`、`zigbee`
- 更新了 `src/opensynaptic/core/pycore/transporter_manager.py` 中的应用协议映射以包括 `matter`、`zigbee`。
- 更新了 `src/opensynaptic/core/physical_layer/manager.py` 中的物理协议候选以包括 `bluetooth`。
- 更新了默认配置播种在：
  - `src/opensynaptic/core/pycore/core.py`
  - `src/opensynaptic/CLI/app.py`
  包括 `matter`、`zigbee` 和 `bluetooth` 的状态/配置默认值。
- 更新了根目录 `Config.json` 的相应状态/配置密钥和合并镜像条目。

### 完成和 UX

- 更新了 `src/opensynaptic/CLI/completion.py` 中的传输器完成描述用于：
  - `matter`
  - `zigbee`
  - `bluetooth`

---

## 审计覆盖更新

驱动程序功能审计覆盖在脚本和插件路径中都得到扩展：

- `scripts/audit_driver_capabilities.py`
- `src/opensynaptic/services/test_plugin/audit_driver_capabilities.py`

添加的审计目标：

- L7：`Matter`、`Zigbee`
- PHY：`Bluetooth`

---

## 文档更新

- 更新了 `docs/TRANSPORTER_PLUGIN.md`：
  - 协议示例现在包括 Matter/Zigbee（应用层）和 Bluetooth（物理层）
  - 更正了 Bluetooth 物理驱动程序路径示例
- 更新了 `docs/CONFIG_SCHEMA.md`：
  - `application_status` 现在记录 MQTT/Matter/Zigbee
  - `physical_status` 现在记录 Bluetooth
  - 扩展了 `application_config` 和 `physical_config` 示例

---

## 执行的验证

### 测试套件

```powershell
py -3 -m pytest tests -q
```

RC 准备期间的观察结果：`4 passed`。

### 驱动程序功能审计

```powershell
py -3 -u scripts/audit_driver_capabilities.py
```

RC 准备期间的观察结果：

- 完整驱动程序：13
- 不完整驱动程序：0
- 错误：0

### 分发验证

```powershell
py -3 -m maturin sdist --manifest-path src/opensynaptic/core/rscore/rust/Cargo.toml --out dist
py -3 -m maturin build --manifest-path src/opensynaptic/core/rscore/rust/Cargo.toml --release --out dist
py -3 -m twine check dist/*
```

RC 准备期间的观察结果：分发检查通过。

---

## RC-1 中的已知约束

- Matter/Zigbee/Bluetooth 实现是面向网关的套接字垫片，而非完整的本地协议栈。
- Zigbee 和 Bluetooth 直接射频/协调器行为仍然依赖于外部硬件网关或专用栈。
- 基于标签的发布作业需要存储库机密和发布环境设置。

---

## 迁移说明

如果升级现有配置，请确保这些密钥存在于 `RESOURCES` 下：

- `application_status.matter`
- `application_status.zigbee`
- `application_config.matter`
- `application_config.zigbee`
- `physical_status.bluetooth`
- `physical_config.bluetooth`
- 相同密钥的 `transporters_status` 镜像条目

核心和 CLI 默认启动现在为新配置或自动修复后的配置播种这些值。

---

## 向 GA 迈进的后续步骤

- 稳定正式网关桥接配置文件（用于 Zigbee ↔ 其他传输流）。
- 为 Matter/Zigbee/Bluetooth 网关适配器添加协议特定的一致性测试。
- 完成公开发布的发布管道权限和标签策略。
