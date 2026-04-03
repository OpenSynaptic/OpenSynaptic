---
title: 第二阶段性能剧本
language: zh
---

# 第二阶段性能剧本（第二个 5 个步骤）

脚本：`scripts/phase2_perf_playbook.py`

## 涵盖内容

- 第一阶段获胜者的稳定性回归
- 同一形状上的核心与端到端分割
- 并发邻域检查
- 收集器冲洗参数扫描
- 门评估+建议

## 快速烟雾测试

```bash
python -u scripts/phase2_perf_playbook.py --total 50000 --repeats 1
```

## 完整运行

```bash
python -u scripts/phase2_perf_playbook.py --total 300000 --repeats 3
```

## 使用特定的第一阶段摘要

```bash
python -u scripts/phase2_perf_playbook.py --phase1-summary data/benchmarks/phase1/phase1_summary_YYYYMMDD_HHMMSS.json --total 300000 --repeats 3
```

## 输出

`data/benchmarks/phase2/phase2_summary_<timestamp>.json`
