---
layout: default
title: OpenSynaptic 文档中心
language: zh
---

# OpenSynaptic 文档中心

使用此页面作为存储库文档的主要入口点。

**快照日期**: 2026-04-04（本地工作区）  
**多语言支持**: [English](../README.md) | [中文](README.md)  
**docs/ 下的总文档**: 滚动更新；详见 [INDEX.md](INDEX.md)

---

## 快速导航

### 运行时快速开始（已验证）
1. 安装：`pip install -e .`
2. Windows 直接启动：`./run-main.cmd run --once --quiet`
3. 通用入口点：`os-node run --once --quiet`
4. 首次运行时的本地恢复行为：[../README.md#first-run-native-auto-repair](../README.md#first-run-native-auto-repair)

### 从这里开始
1. [../README.md](../README.md) - 项目概述和安装说明。
2. [ARCHITECTURE.md](ARCHITECTURE.md) - 系统架构和管道。
3. [plugins/PLUGIN_STARTER_KIT.md](PLUGIN_STARTER_KIT.md) - 插件启动工作流。

### 核心参考

**架构和设计**
- [ARCHITECTURE.md](ARCHITECTURE.md) - 系统架构、2-N-2 管道、融合引擎
- [architecture/](../architecture/) - 详细的架构分析

**API 和配置**
- [API.md](API.md) - API 概览
- [CORE_API.md](CORE_API.md) - Python 核心 API  
- [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md) - 配置参考
- [api/](../api/) - API 详细文档

**Python 和 Rust 集成**
- [PYCORE_RUST_API.md](PYCORE_RUST_API.md) - Pycore 与 Rust 接口
- [RSCORE_API.md](RSCORE_API.md) - Rust 核心 API

### 插件和功能

**插件开发**
- [PLUGIN_DEVELOPMENT_SPECIFICATION.md](PLUGIN_DEVELOPMENT_SPECIFICATION.md) - 插件规范
- [PLUGIN_STARTER_KIT.md](PLUGIN_STARTER_KIT.md) - 插件快速开始
- [plugins/](../plugins/) - 更多插件资源

**功能参考**
- [TRANSPORTER_PLUGIN.md](TRANSPORTER_PLUGIN.md) - 传输插件指南
- [ID_LEASE_SYSTEM.md](ID_LEASE_SYSTEM.md) - ID 租赁系统  
- [ID_LEASE_CONFIG_REFERENCE.md](ID_LEASE_CONFIG_REFERENCE.md) - ID 租赁配置参考

---

## 语言支持

本文档支持以下语言：
- **[English (英文)](../README.md)** - 原始英文文档
- **[中文 (Chinese)](README.md)** - 简体中文翻译

## 贡献文档翻译

如果您想为更多文档添加中文翻译，请：

1. 在 `docs/zh/` 中创建对应的文件
2. 遵循原文的同样结构和格式
3. 提交 Pull Request

---

## 关键改进（OpenSynaptic 2.0+）

- **实时融合引擎**: 高性能二进制数据包生成
- **多传输支持**: UDP、MQTT、UART 等可插拔传输层
- **本地和 Rust 后端**: 灵活选择 Python Pycore 或高性能 Rust 核心
- **ID 租赁系统**: 设备身份管理和分层
- **插件架构**: 轻松扩展传输驱动程序和功能

---

## 常见问题解答

### Q: 如何选择 Python 核心和 Rust 核心？
A: 使用环境变量 `OPENSYNAPTIC_CORE=rscore` 切换到 Rust 核心，或在 Config.json 中设置 `engine_settings.core_backend`。详见 [CONFIG_SCHEMA.md](CONFIG_SCHEMA.md)。

### Q: 如何创建自定义传输驱动程序？
A: 按照 [TRANSPORTER_PLUGIN.md](TRANSPORTER_PLUGIN.md) 中的指南创建新驱动程序。

### Q: 支持哪些平台？
A: Windows、Linux、macOS 均支持。详见主 [README.md](../README.md)。

---

**最后更新**: 2026-04-04  
**反馈和建议**: 请提交 Issue 或 Pull Request
