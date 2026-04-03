---
layout: default
title: OpenSynaptic v1.1.0-rc1 发布说明
language: zh
---

# OpenSynaptic v1.1.0-rc1 发布说明

发布日期：2026-04-01  
发布类型：全面范围的发布候选版本（服务插件生态 + 可视化重构 + 文档工程 + 发布管道整合）

---

## 摘要

v1.1.0-rc1 推动 OpenSynaptic 朝着更好的可扩展性、可观察性和运营可靠性发展。

- 引入统一的 `DisplayAPI`，以便 TUI 和 Web 可以共享统一的显示能力模型。
- **`Port Forwarder` 作为全新内置插件添加**（新插件，而非对旧内置模块的增强）。
- 完成组件化的 Textual TUI 重构并对齐 Web 运行时可视化。
- 加强 CLI/服务生命周期流、测试路径和文档结构。
- 整合打包和发布工作流以减少构建差异。

---

## 版本范围

此发布候选版本涵盖三个层次：

1. 产品层：新插件功能和扩展的可视化路径。
2. 工程层：更强大的 CLI/测试/发布工作流。
3. 知识层：结构化的文档重新组织。

本文档有意排除临时工件、缓存文件、中间构建输出和迁移干扰。

---

## 新增功能

### 1) Display API（统一的显示扩展表面）

主要文件：

- `src/opensynaptic/services/display_api.py`
- `src/opensynaptic/services/builtin_display_providers.py`
- `src/opensynaptic/services/example_display_plugin.py`
- `src/opensynaptic/services/id_allocator_display_example.py`

添加内容：

- 标准化的显示提供程序接口（数据提取 + JSON/HTML/文本格式）。
- 用于独立插件显示部分注册的统一注册表。
- 用于身份、配置、传输、管道、插件和数据库元数据的内置显示部分。

为什么重要：

- 插件可以公开自描述的显示部分，无需修改 UI 核心代码。
- 减少重复的显示逻辑，提高可维护性。

### 2) Port Forwarder（v1.1.0-rc1 中的新内置插件）

新插件文件：

- `src/opensynaptic/services/port_forwarder/__init__.py`
- `src/opensynaptic/services/port_forwarder/main.py`
- `src/opensynaptic/services/port_forwarder/enhanced.py`
- `src/opensynaptic/services/port_forwarder/examples.py`
- `src/opensynaptic/services/port_forwarder/feature_toggle_examples.py`
- `src/opensynaptic/services/port_forwarder/one_to_many_examples.py`

定位（重要）：

- `Port Forwarder` 在本发布候选版本中首次包含在内置插件集中。
- 内置注册在 `src/opensynaptic/services/plugin_registry.py` 中 `PLUGIN_SPECS['port_forwarder']` 下定义。
- 配置条目为 `Config.json` → `RESOURCES.service_plugins.port_forwarder`。

核心功能：

- 用于协议/端口级转发的调度劫持。
- 规则模型支持 `from_protocol/from_port -> to_protocol/to_host/to_port`。
- 支持规则集、优先级、启用/禁用控制和持久化（`rules_file`）。
- 与显示 API 集成以实现运行时规则/状态可见性。

默认配置文件：

- `enabled: true`
- `mode: auto`
- `persist_rules: true`
- `rules_file: data/port_forwarder_rules.json`
- `rule_sets: [default]`

### 3) Textual TUI 组件集

关键文件：

- `src/opensynaptic/services/tui/textual_app.py`
- `src/opensynaptic/services/tui/styles.tcss`
- `src/opensynaptic/services/tui/widgets/*`
- `src/opensynaptic/services/tui/TEXTUAL_REFACTOR_README.md`

添加内容：

- 面板分解（`identity/config/pipeline/transport/plugins/db`）。
- 专用样式层和更清晰的呈现/状态更新边界。
- 用于插件驱动的显示部分的更好扩展点。

---

## 修改内容

### 1) Web 运行时可视化对齐

已更新文件：

- `src/opensynaptic/services/web_user/main.py`
- `src/opensynaptic/services/web_user/handlers.py`
- `src/opensynaptic/services/web_user/templates/index.html`
- `src/opensynaptic/services/web_user/templates/runtime.js`

修改方向：

- 将 Web 输出模型与显示 API 对齐。
- 改进部分呈现和运行时状态公开的一致性。
- 更好的插件/配置状态表示一致性。

### 2) CLI、服务布线和命令解析

已更新文件：

- `src/opensynaptic/CLI/app.py`
- `src/opensynaptic/CLI/build_parser.py`
- `src/opensynaptic/CLI/parsers/service.py`
- `src/opensynaptic/CLI/parsers/test.py`
- `src/opensynaptic/services/service_manager.py`
- `src/opensynaptic/services/plugin_registry.py`

修改方向：

- 更强大的服务插件命令路径。
- 改进的内置插件默认同步行为。
- 别名规范化支持（例如 `port-forwarder -> port_forwarder`）。

### 3) 测试和验证流程加固

已更新文件：

- `src/opensynaptic/services/test_plugin/main.py`
- `src/opensynaptic/services/test_plugin/component_tests.py`
- `src/opensynaptic/services/test_plugin/stress_tests.py`
- `scripts/services_smoke_check.py`
- `scripts/cli_exhaustive_check.py`
- `tests/tui/test_textual_tui.py`
- `tests/unit/test_textual_tui.py`

修改方向：

- 用于服务/CLI/可视化更改的更好的回归路径。
- 针对组件化 TUI 行为的覆盖补充。

### 4) 发布和打包整合

已更新文件：

- `.github/workflows/release.yml`
- `pyproject.toml`
- 已删除 `src/opensynaptic/core/rscore/rust/pyproject.toml`

修改方向：

- 根级 `pyproject.toml` 现在驱动混合项目构建配置。
- 发布作业包含更强大的字段和工件一致性检查。
- 减少根和子项目元数据之间的配置偏差。

---

## 文档更新

此更新是结构性文档重新组织，而不仅仅是内容补充：

- 刷新主要条目文档：`docs/README.md`、`docs/INDEX.md`、`docs/QUICK_START.md`。
- 扩展文档域：`docs/api/`、`docs/architecture/`、`docs/features/`、`docs/plugins/`、`docs/internal/`、`docs/reports/`。
- 为显示 API、TUI 重构、插件规范、性能报告和实现报告添加了重点文档。

结果：简化导航，降低开发、QA 和运维的协作开销。

---

## 兼容性和破坏性变更

### 破坏性变更

- 本发布说明范围内未记录任何协议有线格式破坏性变更。
- 未声明任何核心配置密钥移除。
- 未声明对主要 `OpenSynaptic` 编排条目的替换。

注意：尽管此发布候选版本专注于补充和整合工作，但在生产部署前仍建议进行回归验证。

---

## 升级和迁移指南

### 1) 配置检查

验证有效配置中的这些路径：

- `RESOURCES.service_plugins.port_forwarder`
- `RESOURCES.service_plugins.web_user`
- `RESOURCES.service_plugins.tui`
- `engine_settings.core_backend`

### 2) 最少端口转发器就绪检查

验证：

- `enabled` 状态与部署计划相匹配。
- `mode`（`auto`/`manual`）与服务启动策略相匹配。
- `rules_file` 路径是否可写。
- `rule_sets` 存在且具有有效结构。

### 3) 显示路径验证

- 确认 TUI 可以呈现每个面板部分。
- 确认 Web 可以呈现运行时和插件部分。
- 确认新注册的显示 API 部分是否可被发现。

---

## 推荐验证命令

```powershell
python -u src/main.py plugin-test --suite component
python -u src/main.py plugin-test --suite stress --workers 8 --total 200
python -u src/main.py plugin-test --suite compare --total 10000 --workers 8 --processes 2 --threads-per-process 4 --runs 2 --warmup 1
python -u src/main.py native-check
python -u src/main.py native-build
python scripts/services_smoke_check.py
python scripts/cli_exhaustive_check.py
```

---

## 风险评估

- 功能风险：中低（核心协议路径中未声明的破坏性变更）。
- 运营风险：中（插件和可视化组合不断变化）。
- 发布风险：中低（更强大的构建和工件检查）。
- 文档价值：高（显著的结构性导航改进）。

---

## 包含范围（噪声过滤）

- 服务层：Display API、新 Port Forwarder 插件、ServiceManager/Registry 集成。
- 可视化层：Textual TUI 组件重构、Web 显示模型对齐。
- 工具学：CLI 解析器/服务命令更新、烟雾和穷举检查。
- 测试：更强大的 test_plugin 回归和 TUI 重点测试。
- 发布工程：整合工作流和打包配置。
- 文档：结构化域和扩展的主题特定指南/报告。

---

## 致谢

v1.1.0-rc1 为即将推出的协议和平台迭代建立了更强大的插件和交付基础。
