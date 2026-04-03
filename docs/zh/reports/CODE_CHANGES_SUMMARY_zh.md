---
layout: default
title: 代码变更摘要
language: zh
---

# 代码变更摘要

## 范围

本文档是根据当前本地代码库重构的英文维护版本。

- 文件：`docs/reports/CODE_CHANGES_SUMMARY.md`
- 刷新日期：2026-04-01
- 重点：历史/报告上下文与当前本地工作空间参考重新对齐。

## 代码锚点

- `docs/README.md`
- `docs/INDEX.md`
- `README.md`
- `Config.json`
- `src/opensynaptic/`

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
