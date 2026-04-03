---
title: 插件启动包
language: zh
---

# 插件启动包

## 范围

本文档作为基于当前本地代码库的英文维护版本重建。

- 文件：`docs/plugins/PLUGIN_STARTER_KIT.md`
- 更新日期：2026-04-01
- 重点：插件生命周期、挂载/加载行为、CLI 集成和显示提供程序模式。

## 代码定位点

- `src/opensynaptic/services/service_manager.py`（插件生命周期）
- `src/opensynaptic/services/plugin_registry.py`（内置插件映射和默认值）
- `src/opensynaptic/services/display_api.py`（自发现显示提供程序）
- `src/opensynaptic/services/port_forwarder/main.py`（高级插件示例）
- `src/opensynaptic/services/dependency_manager/main.py`（实用插件示例）

## 实践验证

使用以下命令验证当前工作区中的相关行为：

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

## 备注

- 本页面已规范化为英文并与当前本地路径对齐。
- 对于规范化的运行时行为，建议参考 `src/opensynaptic/` 中的源模块。
