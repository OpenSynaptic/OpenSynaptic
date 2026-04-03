---
title: 发布 1.1.0 RC1 完成
language: zh
---

# 发布 1.1.0 RC1 完成

## 范围

本文档作为基于当前本地代码库的英文维护版本重建。

- 文件：`docs/releases/RELEASE_1_1_0_RC1_COMPLETE.md`
- 更新日期：2026-04-01
- 重点：v1.1.0 RC1 发布的完成状态和验证信息。

## 代码定位点

- `src/opensynaptic/`
- `docs/`
- `README.md`
- 测试套件：`scripts/`、`tests/`

## 实践验证

使用以下命令验证v1.1.0 RC1的功能：

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
- [v1.1.0 发布公告](./v1.1.0_announcement.md)

## 备注

- 本页面已规范化为英文并与当前本地路径对齐。
- 有关v1.1.0 RC1的完整信息，请参考英文原始文档和发布公告。
