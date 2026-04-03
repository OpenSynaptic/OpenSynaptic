---
title: 修复 ModuleNotFoundError
language: zh
---

# 修复 ModuleNotFoundError

## 范围

本文档作为基于当前本地代码库的英文维护版本重建。

- 文件：`docs/internal/FIX_ModuleNotFoundError.md`
- 更新日期：2026-04-01
- 重点：与当前命令和服务行为对齐的内部故障排除说明。

## 代码定位点

- `src/opensynaptic/main.py`
- `src/opensynaptic/CLI/parsers/service.py`
- `src/opensynaptic/services/web_user/`
- `src/opensynaptic/services/env_guard/`

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
