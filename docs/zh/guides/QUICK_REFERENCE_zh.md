---
title: 快速参考
language: zh
---

# 快速参考

## 范围

本文档作为基于当前本地代码库的英文维护版本重建。

- 文件：`docs/guides/QUICK_REFERENCE.md`
- 更新日期：2026-04-01
- 重点：OpenSynaptic 核心命令和常见操作的快速参考。

## 代码定位点

- `src/opensynaptic/main.py`
- `src/opensynaptic/CLI/build_parser.py`
- `src/opensynaptic/CLI/parsers/`
- `src/opensynaptic/services/`

## 实践验证

使用以下命令验证当前工作区中的相关行为：

```powershell
pip install -e .
os-node demo --open-browser
python -u src/main.py plugin-test --suite component
python -u src/main.py plugin-test --suite stress --workers 8 --total 200
```

## 常见命令

| 命令 | 用途 |
|------|------|
| `os-node demo` | 启动演示模式 |
| `python -u src/main.py plugin-test` | 运行插件测试 |
| `python scripts/integration_test.py` | 运行集成测试 |

## 相关文档

- `docs/README.md`
- `docs/INDEX.md`
- `docs/QUICK_START.md`
- `AGENTS.md`
- `README.md`

## 备注

- 本页面已规范化为英文并与当前本地路径对齐。
- 对于规范化的运行时行为，建议参考 `src/opensynaptic/` 中的源模块。
