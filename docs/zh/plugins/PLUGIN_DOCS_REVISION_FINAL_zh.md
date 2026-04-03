---
layout: default
title: 插件文档修订最终版
language: zh
---

# 插件文档修订最终版

## 范围

本文档是根据当前本地代码库重构的英文维护版本。

- 文件：`docs/plugins/PLUGIN_DOCS_REVISION_FINAL.md`
- 刷新日期：2026-04-01
- 重点：插件生命周期、挂载/加载行为、CLI 集成和显示提供程序模式。

## 代码锚点

- `src/opensynaptic/services/service_manager.py`（插件生命周期）
- `src/opensynaptic/services/plugin_registry.py`（内置插件映射和默认值）
- `src/opensynaptic/services/display_api.py`（自发现显示提供程序）
- `src/opensynaptic/services/port_forwarder/main.py`（高级插件示例）
- `src/opensynaptic/services/dependency_manager/main.py`（实用插件示例）

## 实际验证

使用这些命令验证当前工作空间中的相关行为：

```powershell
pip install -e .
python -u src/main.py plugin-test --suite component
python -u src/main.py plugin-test --suite stress --workers 8 --total 200
```

## 相关文档

- `docs/README.md`
- `docs/INDEX.md`
- `docs/QUICK_START.md`
- `AGENTS.md`
- `README.md`

## 说明

- 本页面已规范化为英文，并与当前本地路径对齐。
- 对于规范的运行时行为，优先使用 `src/opensynaptic/` 中的源模块。
