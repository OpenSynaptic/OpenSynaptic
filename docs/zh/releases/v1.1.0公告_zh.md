---
layout: default
title: OpenSynaptic v1.1.0-rc1 公开公告
language: zh
---

# OpenSynaptic v1.1.0-rc1 公开公告

OpenSynaptic v1.1.0-rc1 现已提供。

本候选版本专注于工程成熟度和可扩展性。它在服务插件生态系统、可视化体验、测试流和发布管道上提供了协调升级。对于推出物联网工作负荷的团队，v1.1.0-rc1 旨在使堆栈更易于扩展、更易于观察和更易于可靠地发布。

## 亮点

- 引入统一的 `Display API`，使 TUI 和 Web 共享一个显示能力模型。
- **`Port Forwarder` 作为全新的内置服务插件首次亮相**，支持基于规则的协议/端口转发和运行时可见性。
- TUI 完成了 Textual 组件重构，Web 控制台与新显示模型对齐。
- CLI、服务生命周期工具、测试和文档得到了共同加强。
- 发布和打包工作流进一步整合以保持一致。

## 重要说明：Port Forwarder 是本版本的新增功能

`Port Forwarder` 首次进入内置插件集（不是对旧内置模块的增强）在 v1.1.0-rc1 中。

- 插件注册：`src/opensynaptic/services/plugin_registry.py`（`PLUGIN_SPECS['port_forwarder']`）
- 配置条目：`Config.json` -> `RESOURCES.service_plugins.port_forwarder`
- 默认能力包括规则集、启用/禁用控制和规则持久化（`rules_file`）

## 建议的升级操作（最小化）

1. 验证你的配置中 `RESOURCES.service_plugins.port_forwarder`、`RESOURCES.service_plugins.web_user` 和 `RESOURCES.service_plugins.tui`。
2. 在生产环推出前运行服务烟雾测试和插件测试。
3. 从默认 Port Forwarder 规则集开始，然后逐步引入自定义规则。

## 文档

- 完整发布说明：`docs/releases/v1.1.0.md`
- 文档索引：`docs/INDEX.md`

欢迎来自实际部署的反馈。
