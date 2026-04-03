---
layout: default
title: ID 租赁系统
language: zh
---

# ID 租赁和自适应速率策略系统

**语言**: [English](../ID_LEASE_SYSTEM.md) | [中文](ID_LEASE_SYSTEM.md)

## 概述

OpenSynaptic ID 分配系统实现了一个复杂的基于租赁的 ID 重用机制，具有自适应的速率策略缩短功能。本文档描述了 ID 管理的完整生命周期和配置。

---

## 系统架构

### 核心组件

1. **IDAllocator** (`plugins/id_allocator.py`)
   - 管理 uint32 ID 池分配和重用
   - 处理租赁过期和设备状态跟踪
   - 实现自适应率策略
   - 将所有状态持久化到 `data/id_allocation.json`

2. **租赁配置** (Config.json: `security_settings.id_lease`)
   - 所有策略参数集中配置
   - 在启动时读取，在每次分配时重新评估
   - 可以在不更改代码的情况下更新

3. **指标收集器** (可选回调)
   - 实时发出设备速率和租赁效能指标
   - 可连接到监控/告警系统
   - 包括新设备速率、有效租赁期限和超高速率标志

---

## ID 生命周期

### 状态

每个分配的 ID 都有以下可能的状态：

- **活跃 (Active)**：设备在线，ID 在用，触及时重置租赁
- **离线 (Offline)**：设备离线，租赁倒数开始，租赁到期后可重用 ID
- **已释放 (Released)**：租赁到期后 ID 返回池，可用于新设备

### 分配流

```
新设备 → 查询设备密钥 (MAC/序列号/UUID)
         ↓
    在 _device_index 中找到？ → 是 → 重新激活并重置租赁
                          → 否 → 从 _released 池分配或递增计数器
                                → 记录设备密钥映射
                                → 更新速率指标
```

### 设备重新连接

当具有相同稳定密钥的设备重新连接时：

1. 系统通过稳定密钥（MAC、序列号、UUID 等）检测返回的设备
2. 如果尚未释放，ID 立即被重新激活
3. 租赁重置为基础期限（默认：30 天）
4. `state` 从 "offline" 改为 "active"
5. `last_seen` 和 `offline_since` 计数器更新

---

## 租赁策略参数

所有参数都在 `Config.json` 的 `security_settings.id_lease` 下：

### 基础配置

| 参数 | 默认值 | 类型 | 说明 |
|------|--------|------|------|
| `offline_hold_days` | 30 | int | 可读的保持期（转换为 `base_lease_seconds`） |
| `base_lease_seconds` | 2592000 | int | 新分配或重新触及 ID 的基础租赁（30 天） |
| `min_lease_seconds` | 0 | int | 自适应缩短的下限（0 = 自适应可减至零） |

### 基于速率的自适应缩短

| 参数 | 默认值 | 类型 | 说明 |
|------|--------|------|------|
| `rate_window_seconds` | 3600 | int | 新设备速率的观察窗口（1 小时） |
| `high_rate_threshold_per_hour` | 60 | float | 触发租赁缩短的阈值（设备/小时） |
| `ultra_rate_threshold_per_hour` | 180 | float | 触发强制零租赁的阈值（设备/小时） |
| `high_rate_min_factor` | 0.2 | float | 高速率期间的租赁乘数（0.2 = 基础的 20%） |
| `adaptive_enabled` | true | bool | 启用/禁用自适应租赁缩短 |

---

## 配置示例

### 标准配置（默认）

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
      "high_rate_min_factor": 0.2,
      "adaptive_enabled": true,
      "ultra_force_release": true
    }
  }
}
```

### 高周转环境

```json
{
  "security_settings": {
    "id_lease": {
      "offline_hold_days": 3,
      "base_lease_seconds": 259200,
      "min_lease_seconds": 86400,
      "rate_window_seconds": 1800,
      "high_rate_threshold_per_hour": 120,
      "high_rate_min_factor": 0.5,
      "adaptive_enabled": true
    }
  }
}
```

---

## API 使用

### 基本分配

```python
from opensynaptic.core import OpenSynaptic

node = OpenSynaptic()

# 从服务器请求 ID
success = node.ensure_id("192.168.1.100", 8080)

if success:
    print(f"分配的 ID: {node.assigned_id}")
    print(f"设备标识: {node.device_id}")
```

---

## 自适应租赁算法

有效租赁期限的计算如下：

```python
def calculate_effective_lease(rate_per_hour, base_lease):
    if not adaptive_enabled:
        return base_lease
    
    if rate_per_hour >= ultra_rate_threshold_per_hour:
        if ultra_rate_sustained_for >= ultra_rate_sustain_seconds:
            return 0  # Force-zero: 立即回收
    
    if rate_per_hour <= high_rate_threshold_per_hour:
        return base_lease  # 正常速率：完整租赁期
    
    # 高速率检测：应用因子
    factor = high_rate_threshold_per_hour / rate_per_hour
    factor = max(high_rate_min_factor, min(1.0, factor))
    return max(min_lease_seconds, int(base_lease * factor))
```

### 示例场景

**场景 1：正常设备速率（0-60/小时）**
- 速率：30 设备/小时
- 结果：完整 30 天租赁
- 行为：离线超过 30 天的设备可以回收其 ID

**场景 2：高设备速率（60-180/小时）**
- 速率：120 设备/小时
- 计算：factor = 60 / 120 = 0.5
- 结果：15 天租赁（基数的 50%）
- 行为：更快的 ID 回收以防止池耗尽

**场景 3：超高速率（>180/小时，持续 10+ 分钟）**
- 速率：240 设备/小时，持续 15 分钟
- 结果：0 秒租赁（立即回收）
- 行为：所有离线 ID 立即强制过期，快速回收

---

## 指标与监控

### 发出的指标

`metrics_sink` 回调每 5 秒接收以下指标：

```python
{
    'base_lease_seconds': 2592000,  # 基础配置
    'effective_lease_seconds': 1296000,  # 自适应缩短后
    'new_device_rate_per_hour': 120.5,  # 新分配的滚动速率
    'ultra_rate_active': True,  # 超速率阈值持续
    'force_zero_lease_active': False,  # 当前应用强制零租赁
    'last_reclaim_count': 5,  # 上一个时间间隔回收的 ID
    'last_reclaim_at': 1234567890,  # 最后回收时间戳
    'total_reclaimed': 847,  # 累计回收数
    'allocated_count': 3421,  # 当前分配的 ID 数
    'released_count': 2108,  # 已释放池中的 ID
    'updated_at': 1234567895,  # 指标时间戳
}
```

### 集成示例

```python
def my_metrics_sink(metrics):
    # 发送到监控系统
    prometheus_gauge('id_new_device_rate', metrics['new_device_rate_per_hour'])
    prometheus_gauge('id_effective_lease_seconds', metrics['effective_lease_seconds'])
    prometheus_gauge('id_allocated_count', metrics['allocated_count'])
    if metrics['ultra_rate_active']:
        alert_on_ultra_rate(metrics)

allocator = IDAllocator(
    lease_policy=config['security_settings']['id_lease'],
    metrics_sink=my_metrics_sink,
)
```

---

## 持久化与恢复

ID 分配器将其状态定期写入磁盘以支持故障恢复。

---

### 查询租赁状态

```python
allocator = node.id_allocator

# 获取特定 ID 的信息
info = allocator.get_device_info(device_key="my-device-mac")

print(f"状态: {info['state']}")
print(f"租赁到期: {info['lease_expires_at']}")
print(f"最后看到: {info['last_seen']}")
```

---

## 监控和调试

### CLI 命令

```powershell
# 查看当前分配的 ID
python -u src/main.py snapshot

# 监控 ID 池状态
python -u src/main.py watch --module id_allocator

# 显示配置
python -u src/main.py config-show RESOURCES.id_lease
```

### 日志输出

系统在以下情况时输出日志消息：
- ID 分配：`ID_ALLOCATED`
- ID 重用：`ID_REUSED`
- 租赁取消激活：`LEASE_DEACTIVATED`
- 高速率检测：`HIGH_RATE_DETECTED`

---

## 最佳实践

1. **定期审查租赁参数**：根据您的设备周转速率调整
2. **监控速率指标**：设置告警以检测异常设备朝代
3. **备份 ID 分配文件**：`data/id_allocation.json` 包含设备历史
4. **测试超时**：在生产环境前验证租赁期限是否适当

---

## 常见问题

### Q: ID 永远不会重用？
A: 检查 `security_settings.id_lease.offline_hold_days` 是否太大，或租赁是否已过期。

### Q: 为什么新设备获得不同的 ID？
A: 系统通过设备密钥（MAC/序列号）追踪设备。如果密钥变化，将分配新 ID。

### Q: 如何强制释放所有离线 ID？
A: 设置 `ultra_force_release` 为 `true` 并暂时提高 `ultra_rate_threshold_per_hour` 以触发超高速率模式。

---

**语言**: [English](../ID_LEASE_SYSTEM.md) | [中文](ID_LEASE_SYSTEM.md)  
**最后更新**: 2026-04-04
