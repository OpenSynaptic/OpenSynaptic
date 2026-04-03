---
layout: default
title: 端口转发 1-N 指南
language: zh
---

# 端口转发 1-N 指南

## 范围说明

本文档是基于当前本地代码库的英文维护版本。

- 文件：`docs/features/PORT_FORWARDER_ONE_TO_MANY_GUIDE.md`
- 更新日期：2026-04-01
- 重点：基于当前服务/核心实现的功能行为和运行时切换

## 代码基准点

- `src/opensynaptic/services/port_forwarder/main.py`
- `src/opensynaptic/services/port_forwarder/enhanced.py`
- `src/opensynaptic/core/pycore/transporter_manager.py`
- `src/opensynaptic/core/layered_protocol_manager.py`
- `Config.json`（`RESOURCES.*_status`、`RESOURCES.*_config`）

## 实践验证

使用以下命令验证当前工作空间中的相关行为：

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

- 本文档已规范化为英文格式，并与当前本地路径对齐。
- 对于规范的运行时行为，优先参考 `src/opensynaptic/` 中的源模块。
