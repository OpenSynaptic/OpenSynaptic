---
title: 发布清单
language: zh
---

# 发布清单

## 范围

本文档作为基于当前本地代码库的英文维护版本重建。

- 文件：`docs/releases/RELEASE_CHECKLIST.md`
- 更新日期：2026-04-01
- 重点：新版本发布前的检查清单和验证步骤。

## 代码定位点

- `src/opensynaptic/`
- `docs/`
- `README.md`
- `CHANGELOG.md`

## 实践验证

使用以下命令验证当前工作区中的相关行为：

```powershell
pip install -e .
python -u src/main.py plugin-test --suite component
python -u src/main.py plugin-test --suite stress --workers 8 --total 200
python -u src/main.py plugin-test --suite integration
python -u src/main.py plugin-test --suite audit
```

## 相关文档

- `docs/README.md`
- `docs/INDEX.md`
- `README.md`
- `CHANGELOG.md`
- `AGENTS.md`

## 备注

- 本页面已规范化为英文并与当前本地路径对齐。
- 在发布新版本前，请参考英文原始文档了解完整的检查清单和要求。
