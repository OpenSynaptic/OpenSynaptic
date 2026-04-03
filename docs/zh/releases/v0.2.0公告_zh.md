---
layout: default
title: OpenSynaptic v0.2.0 发布公告
language: zh
---

# OpenSynaptic v0.2.0 发布公告副本

## 可选标题

- OpenSynaptic v0.2.0 已发布：多进程性能调优和 RS 核心加速升级
- OpenSynaptic v0.2.0 已上线：高并发调优、Rust 核心工作流和实用基准示例

---

## 公告正文（准备发布）

我们很高兴地宣布 **OpenSynaptic v0.2.0**。

本版本专注于三个实际结果：

1. **可行的性能优化**：改进了多进程并发指南，用于稳定的高负荷吞吐量。
2. **清晰的 RS 核心（Rust 后端）工作流**：具有端到端操作路径的构建、验证和切换。
3. **更有用的优化示例**：压力运行、自动分析调优、后端对比和 CI 安全检查的完整场景。

### 关键更新

- 多进程控制：`--processes`、`--threads-per-process`、`--batch-size`
- 自动调优控制：`--auto-profile` 和 `--profile-*` 矩阵选项
- RS 核心工具链：`rscore-build`、`rscore-check`、`core --set rscore --persist`
- 对比工作流：`plugin-test --suite compare` 用于 `pycore`/`rscore` 评估

### 为什么要升级到 v0.2.0

- 更快发现机器特定的并发设置，避免重复的手工试验和错误
- 降低 Rust 后端验证和增量推出的切换成本
- 为发布门提供可重复的基准和分析例程

---

## 建议的号召行动

- 升级并运行压力基线：

```powershell
python -u src/main.py plugin-test --suite stress --total 20000 --workers 16 --processes 4 --threads-per-process 4 --batch-size 64
```

- 运行自动配置扫描：

```powershell
python -u src/main.py plugin-test --suite stress --auto-profile --profile-total 50000 --profile-runs 1 --final-runs 1 --profile-processes 1,2,4,8 --profile-threads 4,8,16 --profile-batches 32,64,128
```

- 构建、检查和切换 RS 核心：

```powershell
python -u src/main.py rscore-build
python -u src/main.py rscore-check
python -u src/main.py core --set rscore --persist
```
