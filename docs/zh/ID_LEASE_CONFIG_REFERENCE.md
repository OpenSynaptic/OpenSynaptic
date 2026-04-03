---
layout: default
title: ID 租赁配置速查表
language: zh
---

# ID 租赁配置速查表

**语言**: [English](../ID_LEASE_CONFIG_REFERENCE.md) | [中文](ID_LEASE_CONFIG_REFERENCE.md)

快速参考所有 ID 租赁配置选项。详细文档见 [ID_LEASE_SYSTEM.md](ID_LEASE_SYSTEM.md)。

---

## 默认配置

```json
{
  "security_settings": {
    "id_lease": {
      "offline_hold_days": 30,
      "base_lease_seconds": 2592000,
      "min_lease_seconds": 0,
      "rate_window_seconds": 3600,
      "high_rate_threshold_per_hour": 60,
      "ultra_rate_threshold_per_hour": 180,
      "ultra_rate_sustain_seconds": 600,
      "high_rate_min_factor": 0.2,
      "adaptive_enabled": true,
      "ultra_force_release": true
    }
  }
}
```

---

## 配置矩阵

| 参数 | 默认 | 范围 | 说明 |
|------|------|------|------|
| `offline_hold_days` | 30 | 1–3650 | 离线设备保持 ID 的天数 |
| `base_lease_seconds` | 2592000 | 3600–31536000 | 基础租赁（秒）(1小时–1年) |
| `min_lease_seconds` | 0 | 0–2592000 | 最小租赁（0 = 支持自动释放） |
| `rate_window_seconds` | 3600 | 300–86400 | 速率观察窗口（5分钟–1天） |
| `high_rate_threshold_per_hour` | 60 | 10–1000 | 高速率触发点（设备/小时） |
| `ultra_rate_threshold_per_hour` | 180 | 50–10000 | 超高速率触发点（设备/小时） |
| `high_rate_min_factor` | 0.2 | 0.0–1.0 | 高速率期间的租赁因子 |
| `adaptive_enabled` | true | true/false | 启用自适应缩短 |
| `ultra_force_release` | true | true/false | 超高速率后立即释放 |

---

## 场景配置

### 场景 1：长期稳定设备

```json
{
  "offline_hold_days": 90,
  "base_lease_seconds": 7776000,
  "adaptive_enabled": false
}
```

**用途**：固定部署（工厂、农业）
**特点**：长租赁，很少重用 ID

### 场景 2：高周转移动设备

```json
{
  "offline_hold_days": 3,
  "base_lease_seconds": 259200,
  "high_rate_threshold_per_hour": 120,
  "high_rate_min_factor": 0.5
}
```

**用途**：移动设备、临时传感器
**特点**：短租赁，频繁 ID 重用

### 场景 3：大规模部署（ID 池稀缺）

```json
{
  "offline_hold_days": 1,
  "base_lease_seconds": 86400,
  "min_lease_seconds": 3600,
  "ultra_rate_threshold_per_hour": 500,
  "ultra_force_release": true
}
```

**用途**：受限 ID 空间、高设备周转
**特点**：最小化 ID 保留，激进重用

---

## 调整指南

### 如果 ID 池耗尽太快

1. **降低** `base_lease_seconds`（例如 30 天 → 7 天）
2. **降低** `offline_hold_days`（例如 30 → 7）
3. **启用** `adaptive_enabled = true`
4. **降低** `high_rate_threshold_per_hour`（更容易触发租赁缩短）

### 如果 ID 重被用于不同设备

1. **增加** `offline_hold_days`（给设备更多时间重新连接）
2. **增加** `base_lease_seconds`（更长的保留期）
3. **禁用** `adaptive_enabled = false`（防止缩短）

### 如果新设备注册失败

1. 检查 `Server_Core.Start_ID` 和 `End_ID` 范围是否足够大
2. 检查 `offline_hold_days` 是否太高（所有 ID 被离线占用）
3. 使用 `plugin-test --suite integration` 测试 ID 分配

---

## 监控命令

```powershell
# 显示当前 ID 配置
python -u src/main.py config-show security_settings.id_lease

# 实时监控 ID 分配
python -u src/main.py watch --module id_allocator

# 查看 JSON 状态
python -u src/main.py snapshot | grep id_allocator
```

---

## 常用修改

### 快速切换到激进重用

```powershell
python -u src/main.py config-set security_settings.id_lease.offline_hold_days 1 
python -u src/main.py config-set security_settings.id_lease.base_lease_seconds 86400
```

### 切换到保守策略

```powershell
python -u src/main.py config-set security_settings.id_lease.offline_hold_days 90
python -u src/main.py config-set security_settings.id_lease.adaptive_enabled false
```

---

## 常见错误

### ❌ 不提供稳定的设备密钥

```python
# 错误：每次连接都获得新 ID
allocator.allocate_id(meta={'timestamp': time.time()})

# 正确：为返回的设备重用 ID
allocator.allocate_id(meta={'device_id': 'sensor_123', 'mac': 'AA:BB:CC:DD:EE:FF'})
```

### ❌ 设置 `min_lease_seconds` 过高

```python
# 错误：自适应缩短无法帮助
"min_lease_seconds": 604800  # 7 天最小
"high_rate_threshold_per_hour": 60.0

# 正确：自适应可根据需要缩短至零
"min_lease_seconds": 0  # 允许强制零
```

### ❌ 断开连接时忘记调用 `release_id()`

```python
# 错误：设备离线但 ID 被无限期持有
if device_disconnects:
    pass  # 忘记释放！

# 正确：标记 ID 离线，启动租赁倒计时
if device_disconnects:
    allocator.release_id(device_id, immediate=False)
```

### ❌ 不监控指标

```python
# 错误：无法看到 ID 分配健康状态
allocator = IDAllocator(base_dir='.')

# 正确：实时指标用于调试
def metrics_sink(metrics):
    log_to_monitoring_system(metrics)

allocator = IDAllocator(base_dir='.', metrics_sink=metrics_sink)
```

---

## 何时调整配置

1. **初始部署后**
   - 在生产环境运行 1-2 周
   - 监控 `new_device_rate_per_hour` 和 `effective_lease_seconds`
   - 根据观察到的模式调整阈值

2. **在扩展事件期间**
   - 预期注册激增？增加 `ultra_rate_threshold_per_hour`
   - 设备生命周期缩短？减少 `base_lease_seconds`
   - 网络迁移？临时禁用 `adaptive_enabled`

3. **在警报响应时**
   - "ID 池耗尽"警报？启用 `ultra_force_release`
   - "ID 重用太快"警报？提高 `offline_hold_days`

1. 检查 `Server_Core.Start_ID` 和 `End_ID` 范围是否足够大
2. 检查 `offline_hold_days` 是否太高（所有 ID 被离线占用）
3. 使用 `plugin-test --suite integration` 测试 ID 分配

---

## 监控命令

```powershell
# 显示当前 ID 配置
python -u src/main.py config-show security_settings.id_lease

# 实时监控 ID 分配
python -u src/main.py watch --module id_allocator

# 查看 JSON 状态
python -u src/main.py snapshot | grep id_allocator
```

---

## 常用修改

### 快速切换到激进重用

```powershell
python -u src/main.py config-set security_settings.id_lease.offline_hold_days 1
python -u src/main.py config-set security_settings.id_lease.base_lease_seconds 86400
```

### 切换到保守策略

```powershell
python -u src/main.py config-set security_settings.id_lease.offline_hold_days 90
python -u src/main.py config-set engine_settings.precision security_settings.id_lease.adaptive_enabled false
```

---

**语言**: [English](../ID_LEASE_CONFIG_REFERENCE.md) | [中文](ID_LEASE_CONFIG_REFERENCE.md)  
**最后更新**: 2026-04-04
