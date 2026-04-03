---
layout: default
title: 架构 FFI 分析
language: zh
---

# 架构 FFI 分析

## 范围说明

本文档是基于当前本地代码库的英文维护版本。

- 文件：`docs/architecture/ARCHITECTURE_FFI_ANALYSIS.md`
- 更新日期：2026-04-01
- 重点：来自当前核心模块的运行时架构、后端选择和管道边界

## 代码基准点

- `src/opensynaptic/core/pycore/core.py`
- `src/opensynaptic/core/coremanager.py`
- `src/opensynaptic/core/layered_protocol_manager.py`
- `src/opensynaptic/core/rscore/`
- `src/opensynaptic/services/`

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
