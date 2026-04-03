---
title: 重构快速参考
language: zh
---

# 重构快速参考

## 范围

本文档作为基于当前本地代码库的英文维护版本重建。

- 文件：`docs/guides/REFACTORING_QUICK_REFERENCE.md`
- 更新日期：2026-04-01
- 重点：代码重构指南和最佳实践。

## 代码定位点

- `src/opensynaptic/core/`
- `src/opensynaptic/services/`
- `src/opensynaptic/utils/`

## 重构原则

1. **保持向后兼容** - 尽可能避免破坏性更改
2. **增量式重构** - 逐步进行，充分测试
3. **文档同步** - 更新代码时同时更新文档
4. **性能验证** - 重构前后进行性能对比

## 实践验证

使用以下命令验证重构的影响：

```powershell
pip install -e .
python -u src/main.py plugin-test --suite component
python -u src/main.py plugin-test --suite stress --workers 8
python -u src/main.py plugin-test --suite integration
```

## 重构检查清单

- [ ] 代码改动不超过 500 行单次提交
- [ ] 包含单元测试覆盖新/修改的代码
- [ ] 运行完整集成测试无失败
- [ ] 文档同步更新
- [ ] 性能基准测试验证无回退

## 相关文档

- `docs/README.md`
- `docs/INDEX.md`
- `docs/ARCHITECTURE.md`
- `AGENTS.md`
- `README.md`

## 备注

- 本页面已规范化为英文并与当前本地路径对齐。
- 重构工作应严格遵循本指南的原则和检查清单。
