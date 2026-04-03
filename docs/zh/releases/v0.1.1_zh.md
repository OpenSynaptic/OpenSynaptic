---
layout: default
title: OpenSynaptic v0.1.1 发布说明
language: zh
---

# OpenSynaptic v0.1.1 发布说明

发布日期：2026-03-16  
类型：文档 + 并发和 RS 核心能力说明

---

## 亮点

- 为 `v0.1.1` 添加了完整的发布说明，整合了多进程和 RS 核心指南。
- 澄清了压力测试并发控制和自动分析工作流。
- 澄清了 `rscore`（Rust 核心）构建/检查/切换工作流和回退行为。
- 更新了文档导航以指向本版本。

---

## 多进程和并发更新

`plugin-test` 现在具有明确记录和准备好调优的并发控制：

- `--processes`：用于压力执行的 OS 进程数（`1` 表示仅线程模式）。
- `--threads-per-process`：每个进程中的线程计数（默认为 `--workers`）。
- `--batch-size`：每个 future 的任务批处理大小，以减少调度程序开销。
- `--auto-profile`：扫描候选进程/线程/批处理组合并选择最佳配置文件。
- `--profile-processes`、`--profile-threads`、`--profile-batches`：定义候选矩阵。
- `--profile-total`、`--profile-runs`、`--final-runs`：控制扫描和最终测量工作负载。

相关套件和选项：

- `--suite stress` 用于压力吞吐量验证。
- `--suite compare` 用于具有测量运行的后端对比。
- `--suite full_load` 用于配置文件驱动的满负荷运行。
- `--component-processes` 用于单独 OS 进程中的分量测试。

参考路径：

- `src/opensynaptic/CLI/app.py`
- `src/opensynaptic/services/test_plugin/stress_tests.py`

---

## RS 核心（rscore）更新

本版本端到端记录了 RS 核心工作流：

- 构建 Rust 核心共享库：
  - `os-node rscore-build`
  - 或 `python -u src/main.py rscore-build`
- 检查 RS 核心运行时可用性：
  - `os-node rscore-check`
  - 或 `python -u src/main.py rscore-check`
- 显式切换后端：
  - `os-node core --set rscore`
  - 或使用 `--persist` 选项持久化至 `engine_settings.core_backend`
- 在原生 C 构建流中包含 RS 构建：
  - `python -u src/main.py native-build --include-rscore`

`rscore-check` 报告：

- Rust DLL 加载状态
- 解析的 DLL 路径和存在性
- cargo 可用性
- 活跃核心和可用核心

行为说明：

- 如果 RS 原生 DLL 不可用，运行时可以保留在 `pycore` 上。
- 测试流中的 `--require-rust` 可以在 RS 原生路径不可用时强制硬失败。

参考路径：

- `src/opensynaptic/core/rscore/build_rscore.py`
- `src/opensynaptic/CLI/app.py`
- `docs/RSCORE_API.md`
- `docs/PYCORE_RUST_API.md`

---

## 破坏性变更

- 无。

本版本中没有协议段格式、数据包架构或必需配置密钥的删除。

---

## 迁移指南

无强制运行时迁移。

推荐操作：

1. 在 `Config.json` 中保持 `engine_settings.core_backend` 明确（`pycore` 或 `rscore`）。
2. 对于 RS 部署，在切换核心前运行 `rscore-build` 并使用 `rscore-check` 进行验证。
3. 对于吞吐量调优，使用 `--auto-profile` 运行压力测试，并在你的 CI 文档中持久化选定的并发设置。

---

## 验证

基于上面的推荐内容，建议运行：

```powershell
python -u src/main.py plugin-test --suite stress --total 5000 --workers 8 --processes 2 --threads-per-process 4 --batch-size 64
python -u src/main.py rscore-check
python -u src/main.py plugin-test --suite compare --total 5000 --runs 1
```
