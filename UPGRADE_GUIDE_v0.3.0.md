# OpenSynaptic v0.3.0 快速升级指南

**目标:** 从 v0.2.0 升级到 v0.3.0  
**预计时间:** 15-30 分钟  
**难度:** ⭐ 简单 (100% 兼容)

---

## ⚡ 5分钟快速开始

### 方案 1: 自动升级 (推荐)

```powershell
# 1. 更新代码
cd E:\新建文件夹\OpenSynaptic
git pull origin main
# 或: 直接复制新版本文件

# 2. 验证安装
python -u src/main.py verify_deployment.py

# 3. 运行集成测试
python -u src/main.py plugin-test --suite stress --total 5000 --workers 8

# 完成! 现在您正在使用 v0.3.0
```

### 方案 2: 全新部署

```powershell
# 1. 安装依赖
cd E:\新建文件夹\OpenSynaptic
pip install -e .

# 2. 验证
python -u verify_deployment.py

# 3. 初始化 ID 系统
python -u test_id_lease_system.py

# 完成!
```

---

## 📋 详细升级步骤

### 步骤 1: 准备 (5 分钟)

```powershell
# 检查当前版本
python -u src/main.py --version
# 应该输出: v0.2.0 或更早

# 备份当前配置
Copy-Item Config.json Config.json.backup
```

### 步骤 2: 更新代码 (2 分钟)

选择其中一个:

**选项 A - 使用 Git (推荐)**
```powershell
git pull origin main
```

**选项 B - 手动复制**
- 从 v0.3.0 复制以下文件到您的项目:
  - 所有 `docs/` 下的新文件
  - `plugins/id_allocator_optimized.py`
  - `scripts/` 下的所有新脚本
  - 更新 `README.md`, `CHANGELOG.md`, `AGENTS.md`

### 步骤 3: 验证部署 (3 分钟)

```powershell
# 运行部署验证脚本
python -u verify_deployment.py

# 预期输出:
# ✅ Checking file existence...
# ✅ Validating configuration...
# ✅ IDAllocator initialization test...
# ✅ Parameter verification...
# ✅ Deployment Summary
# Status: READY FOR PRODUCTION
```

### 步骤 4: 初始化 ID 系统 (2 分钟)

**可选但推荐:**

```powershell
# 运行 ID 租赁测试 (初始化数据)
python -u test_id_lease_system.py

# 预期: 5/5 测试通过
# ✅ Test 1: Basic allocation
# ✅ Test 2: Reconnection
# ✅ Test 3: Adaptive shortening
# ✅ Test 4: Metrics emission
# ✅ Test 5: Persistence
```

### 步骤 5: 功能验证 (5-10 分钟)

```powershell
# 验证驱动能力
python -u scripts/audit_driver_capabilities.py

# 预期输出:
# ================================================================================
# SUMMARY
# ================================================================================
# Complete (Send + Receive):   10  ✅
# Incomplete (Missing Receive): 0
# Error:                        0
```

### 步骤 6: 性能验证 (10 分钟)

```powershell
# 运行压力测试确保无性能回退
python -u src/main.py plugin-test --suite stress `
  --total 10000 --workers 8 `
  --processes 2 --threads-per-process 4 `
  --batch-size 64

# 记录吞吐量、延迟、CPU使用率
# 与之前的基准对比 (应该相同或更好)
```

---

## 🔧 配置优化 (可选)

### 启用 ID 租赁系统

编辑 `Config.json`, 添加以下部分:

```json
{
  // ... 其他配置 ...
  
  "id_lease_system": {
    "enabled": true,
    "offline_hold_days": 30,
    "base_lease_seconds": 2592000,
    "min_lease_seconds": 0,
    "rate_window_seconds": 3600,
    "high_rate_threshold_per_hour": 60,
    "ultra_rate_threshold_per_hour": 180,
    "ultra_rate_sustain_seconds": 600,
    "high_rate_min_factor": 0.2,
    "adaptive_enabled": true,
    "ultra_force_release": true,
    "metrics_emit_interval_seconds": 5
  }
}
```

### 选择预设场景

**场景 1: 高流动 IoT 网络** (设备频繁连接/断开)
```json
{
  "offline_hold_days": 7,
  "base_lease_seconds": 604800,
  "high_rate_threshold_per_hour": 100,
  "adaptive_enabled": true
}
```

**场景 2: 工业监控** (稳定长期运行)
```json
{
  "offline_hold_days": 90,
  "base_lease_seconds": 7776000,
  "high_rate_threshold_per_hour": 10,
  "adaptive_enabled": false
}
```

**场景 3: 开发/测试** (便于调试)
```json
{
  "offline_hold_days": 1,
  "base_lease_seconds": 86400,
  "high_rate_threshold_per_hour": 1000,
  "adaptive_enabled": true,
  "metrics_emit_interval_seconds": 1
}
```

---

## ✅ 升级完成检查清单

- [ ] 代码已更新
- [ ] `verify_deployment.py` 通过
- [ ] 集成测试通过 (8/8 PASS)
- [ ] 驱动审计完成 (10/10)
- [ ] 性能基准通过 (无回退)
- [ ] Config.json 已备份
- [ ] ID 租赁系统已配置 (可选)

**✅ 升级成功!**

---

## 🆘 故障排查

### 问题 1: 文件丢失错误

```
FileNotFoundError: docs/ID_LEASE_SYSTEM.md
```

**解决:**
- 确保已复制所有新文件
- 检查 `docs/` 目录是否包含新文档
- 重新运行 git pull 或手动复制

### 问题 2: 导入错误

```
ImportError: No module named 'opensynaptic.plugins.id_allocator_optimized'
```

**解决:**
```powershell
# 重新安装包
pip install -e .
```

### 问题 3: ID 数据损坏

```
json.JSONDecodeError: data/id_allocation.json
```

**解决:**
```powershell
# 删除损坏的数据文件
Remove-Item data/id_allocation.json

# 重新初始化
python -u test_id_lease_system.py
```

### 问题 4: 版本冲突

```
Version mismatch: expected v0.3.0, got v0.2.0
```

**解决:**
```powershell
# 检查 pyproject.toml
# 确保版本号已更新为 0.3.0

# 或强制重新加载
python -u -c "from opensynaptic import __version__; print(__version__)"
```

---

## 📊 升级前后对比

### 升级前 (v0.2.0)

```powershell
> os-node --list-drivers
UDP     ✓ send
TCP     ✓ send
QUIC    ✓ send
... (接收功能全部缺失)

> 性能: 基准值 (100%)
> 文档: 12个文档
> 测试: 基础覆盖
```

### 升级后 (v0.3.0)

```powershell
> os-node --list-drivers
UDP     ✓ send ✓ listen
TCP     ✓ send ✓ listen
QUIC    ✓ send ✓ listen (async)
... (全部双向完整)

> 性能: 相同或更好 (100%+)
> 文档: 19个文档 (+880 行)
> 测试: 完整覆盖 (8/8)
```

---

## 🚀 升级后推荐操作

### 1. 学习新功能 (30 分钟阅读)

```powershell
# 查看关键文档
code docs/ID_LEASE_SYSTEM.md
code DRIVER_QUICK_REFERENCE.md
code docs/ID_LEASE_CONFIG_REFERENCE.md
```

### 2. 测试双向通信 (15 分钟)

```powershell
# 运行双向通信示例
python scripts/example_bidirectional.py

# 或创建您自己的测试:
# from opensynaptic.core.transport_layer.drivers import udp
# udp.listen({"host": "0.0.0.0", "port": 5000}, callback)
```

### 3. 集成 ID 管理 (20 分钟)

```python
from opensynaptic.services.id_lease_system import IDLeaseManager

lease_mgr = IDLeaseManager(config_path="Config.json")
device_id = lease_mgr.get_or_allocate_id("sensor_001")
lease_mgr.record_device_activity(device_id)
```

### 4. 监控指标 (10 分钟)

```python
def on_metrics(metrics):
    print(f"Active: {metrics['active_count']}")
    print(f"Pending: {metrics['pending_release_count']}")
    print(f"Rate: {metrics.get('rate_per_hour', 0)}")

lease_mgr.set_metrics_sink(on_metrics)
```

---

## 📞 需要帮助?

### 文档

| 文档 | 用途 |
|------|------|
| `README.md` | 项目概览 |
| `docs/ID_LEASE_SYSTEM.md` | ID系统详细文档 |
| `docs/ID_LEASE_CONFIG_REFERENCE.md` | 配置和故障排查 |
| `DRIVER_QUICK_REFERENCE.md` | 驱动接口速查表 |
| `AGENTS.md` | AI集成指南 |
| `VERSION_COMPARISON_REPORT.md` | v0.2.0 vs v0.3.0 对比 |

### 常见问题

**Q: 升级会影响现有功能吗?**  
A: 不会。v0.3.0 完全向后兼容 v0.2.0。所有现有代码无需修改。

**Q: 需要迁移数据吗?**  
A: 不需要。Config.json 可以直接使用，新的 ID 租赁字段会自动补充。

**Q: 性能会下降吗?**  
A: 不会。继承了 v0.2.0 的所有性能优化。ID 管理开销 <2%。

**Q: 可以回滚吗?**  
A: 可以。备份了 Config.json.backup，可以恢复到旧版本。

**Q: 如何验证升级成功?**  
A: 运行 `verify_deployment.py` 和 `audit_driver_capabilities.py`。

---

## 🎉 升级成功标志

您将看到:

```powershell
# 1. 验证通过
✅ Deployment verification: PASS
✅ Configuration validation: PASS
✅ IDAllocator test: PASS

# 2. 驱动完整
✅ Complete drivers: 10/10
✅ Bidirectional: 100%

# 3. 性能稳定
✅ Performance: 无回退
✅ Throughput: 保持或提升
✅ Latency: <5ms

# 4. 新功能可用
✅ ID lease system ready
✅ Adaptive management active
✅ Metrics enabled

# 现在您正在运行 v0.3.0!
```

---

## 📈 下一步

升级完成后，建议:

1. **阅读** `docs/ID_LEASE_SYSTEM.md` (架构和最佳实践)
2. **配置** 根据您的场景选择预设或自定义配置
3. **测试** 运行 `scripts/integration_test.py` 验证所有功能
4. **集成** 在您的应用中使用新的 ID 管理 API
5. **监控** 设置指标收集，跟踪设备连接

---

**升级指南完成**

问题? 查看故障排查章节或阅读相关文档。

**祝升级顺利!** 🎉

---

最后更新: 2026-03-24  
适用版本: v0.2.0 → v0.3.0  
兼容性: ✅ 完全向后兼容

