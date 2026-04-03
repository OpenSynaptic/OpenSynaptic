---
layout: default
title: OpenSynaptic v0.3.0 发布文档摘要
language: zh
---

# OpenSynaptic v0.3.0 发布文档摘要

本页是 `v0.3.0` 发布材料的紧凑索引。

---

## 主要发布文档

- 详细的发布公告（发布来源）：`docs/releases/v0.3.0_announcement_en.md`
- 稳定索引路径：`docs/releases/v0.3.0_announcement.md`
- 升级指南：`docs/guides/upgrade/v0.3.0.md`
- 版本对比报告：`docs/reports/releases/v0.2.0-v0.3.0-comparison.md`

---

## 建议阅读顺序

### 产品和利益相关者受众

1. `docs/releases/v0.3.0_announcement_en.md`
2. `docs/reports/releases/v0.2.0-v0.3.0-comparison.md`
3. `docs/guides/upgrade/v0.3.0.md`

### 工程和运维受众

1. `docs/guides/upgrade/v0.3.0.md`
2. `docs/ID_LEASE_SYSTEM.md`
3. `docs/ID_LEASE_CONFIG_REFERENCE.md`

---

## 验证速查清单

```powershell
python -u verify_deployment.py
python -u scripts/audit_driver_capabilities.py
python -u scripts/integration_test.py
```
