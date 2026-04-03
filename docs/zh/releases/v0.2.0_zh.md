---
layout: default
title: OpenSynaptic v0.2.0 发布说明
language: zh
---

# OpenSynaptic v0.2.0 发布说明

发布日期：2026-03-16  
类型：性能优化 + 多进程和 RS 核心工作流增强

---

## 亮点

- 升级发布线至 `v0.2.0`，采用清晰的性能导向叙述。
- 整合多进程压力调优、配置扫描和 RS 核心操作指南。
- 添加了用于高负载验证和后端切换的优化用法示例。
- 保持与现有协议段格式和配置结构的兼容性。

---

## 性能优化

本版本强调了实际吞吐量和运行时效率的改进：

- 多进程压力并发现在明确记录为生产级基准测试。
- 自动分析工作流（`--auto-profile`）突出用于选择进程/线程/批处理组合。
- 通过 `--batch-size` 和配置候选矩阵添加调度程序开销调优指南。
- RS 核心路径（`rscore`）的用法为原生加速和后端可比性进行了澄清。

关键优化控制：

- `--processes`
- `--threads-per-process`
- `--batch-size`
- `--auto-profile`
- `--profile-processes`、`--profile-threads`、`--profile-batches`
- `--profile-total`、`--profile-runs`、`--final-runs`

---

## 优化的用法示例

### 1) 高吞吐量多进程压力测试

```powershell
python -u src/main.py plugin-test --suite stress --total 20000 --workers 16 --processes 4 --threads-per-process 4 --batch-size 64
```

### 2) 自动分析最佳并发矩阵

```powershell
python -u src/main.py plugin-test --suite stress --auto-profile --profile-total 50000 --profile-runs 1 --final-runs 1 --profile-processes 1,2,4,8 --profile-threads 4,8,16 --profile-batches 32,64,128
```

### 3) 在受控负载下对比 pycore vs rscore

```powershell
python -u src/main.py plugin-test --suite compare --total 10000 --workers 8 --processes 2 --threads-per-process 4 --runs 2 --warmup 1
```

### 4) 构建并切换到 RS 核心以加速路径

```powershell
python -u src/main.py rscore-build
python -u src/main.py rscore-check
python -u src/main.py core --set rscore --persist
```

### 5) 在 CI 中强制使用 RS 原生路径

```powershell
python -u src/main.py plugin-test --suite stress --total 5000 --workers 8 --processes 2 --require-rust
```

---

## RS 核心（rscore）说明

- 构建：`os-node rscore-build` / `python -u src/main.py rscore-build`
- 检查：`os-node rscore-check` / `python -u src/main.py rscore-check`
- 切换：`os-node core --set rscore [--persist]`
- 整合原生构建：`python -u src/main.py native-build --include-rscore`

`rscore-check` 显示运行时准备就绪的详细信息：

- RS DLL 加载状态
- DLL 路径和存在性
- cargo 可用性
- 活跃核心和可用核心

如果 RS DLL 不可用，运行时可以停留在 `pycore`；测试流可以通过 `--require-rust` 强制 RS 要求。

---

## 破坏性变更

- 无。

v0.2.0 中没有引入协议数据包架构或必需配置密钥的删除。

---

## 迁移指南

无强制迁移要求。

推荐的升级步骤：

1. 在 `Config.json` 中显式将 `engine_settings.core_backend` 固定为 `pycore` 或 `rscore`。
2. 对于 RS 部署，在切换后端之前执行 `rscore-build`，然后使用 `rscore-check` 进行验证。
3. 对于性能敏感的环境，为每个硬件类运行一次 `--auto-profile` 传递，并在 CI/CD 文档中保留选定的参数。

---

## 验证

```powershell
python -u src/main.py rscore-check
python -u src/main.py plugin-test --suite stress --total 5000 --workers 8 --processes 2 --threads-per-process 4 --batch-size 64
python -u src/main.py plugin-test --suite stress --auto-profile --profile-total 20000 --final-runs 1
python -u src/main.py plugin-test --suite compare --total 5000 --runs 1 --warmup 0 --processes 2
```

可选的扩展验证：

```powershell
python -u src/main.py native-check
python -u src/main.py native-build --include-rscore
python -u src/main.py core --set rscore --persist
python -u src/main.py plugin-test --suite all --workers 8 --total 200
```

---

## 已知问题

- IDE/静态分析可能会显示过期的解析诊断信息，直到语言服务重新索引/重启为止。
- RS 原生路径依赖于本地 Rust 工具链和构建的共享库可用性。
- 多进程基准测试结果因 CPU 拓扑、进程亲和力和 Windows 调度程序行为而异。

---

## 更新的文档

- 已更新 `README.md`
- 已更新 `docs/README.md`
- 已更新 `CHANGELOG.md`
- 已添加 `docs/releases/v0.2.0.md`
