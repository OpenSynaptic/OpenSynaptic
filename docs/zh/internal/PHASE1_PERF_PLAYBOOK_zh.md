---
title: 第一阶段性能剧本
language: zh
---

# 第一阶段性能剧本（前 5 个步骤）

本剧本自动化了 `plugin-test` 压力的前五个优化步骤。

## 功能

1. 冻结目标元数据（`target_throughput_pps=1000000`）。
2. 运行基准/并发矩阵。
3. 从结果中提取瓶颈诊断。
4. 按吞吐量选择最佳并发形状。
5. 在最佳形状上运行批邻域。

## 脚本

- `scripts/phase1_perf_playbook.py`

## 快速烟雾测试（快速）

```bash
python -u scripts/phase1_perf_playbook.py --total 20000 --repeats 1 --chain-mode e2e
```

## 完整运行（繁重）

```bash
python -u scripts/phase1_perf_playbook.py --total 1000000 --repeats 3 --chain-mode e2e
```

## 可选自定义配置

```bash
python -u scripts/phase1_perf_playbook.py --config data/benchmarks/Config_e2e_flush1024.json --total 1000000 --repeats 2 --chain-mode e2e
```

## 输出

所有工件都写入到 `data/benchmarks/phase1/` 下：

- `target_<timestamp>.json`
- `bottleneck_<timestamp>.json`
- `phase1_summary_<timestamp>.json`
- 每次运行的原始基准文件

摘要包括最佳并发和批候选、吞吐量基准统计和瓶颈分解。
