# OpenSynaptic v1.4.0 发布说明

> 发布日期：2026-04-07  
> 对应 tag：`v1.4.0`  
> 变更范围：`src/opensynaptic/services/port_forwarder/`

---

## 概述

v1.4.0 完成了 `EnhancedPortForwarder` 的正式集成。该组件最初作为独立草稿存在于 `enhanced.py`，从未被任何生产代码引用。本版本对其进行了完整重写，修复了三个阻塞性缺陷，并将其并入继承体系，成为 `PortForwarder` 的功能超集。

---

## 新增功能

### EnhancedPortForwarder（正式集成）

`EnhancedPortForwarder` 现在继承自 `PortForwarder`，在父类规则集路由的基础上新增 7 步数据包处理流水线：

```
1. Middleware before_dispatch  → 前置钩子，可修改 packet
2. FirewallRule 防火墙检查     → 阻断 denied 包，返回 False
3. TrafficShaper 流量整形      → 令牌桶限速，超限直接 drop（非阻塞）
4. ProtocolConverter 协议转换  → 可选的 bytes 变换
5. ProxyRule 代理转发          → 真实 UDP/TCP socket 转发，失败回退原包
6. _route_and_dispatch 路由    → 父类规则集匹配 + transport 分发
7. Middleware after_dispatch   → 后置钩子，接收分发结果
```

**新增组件类：**

| 类 | 说明 |
|----|------|
| `FirewallRule` | 基于协议/IP/端口范围/包大小的有状态防火墙规则，支持 allow/deny 动作，带优先级排序 |
| `TrafficShaper` | 令牌桶算法限速，`can_send()` 完全非阻塞，`get_wait_time()` 仅供上层参考 |
| `ProtocolConverter` | 可插拔的 `transform_func` 字节变换，无匹配时原包透传 |
| `Middleware` | before/after 双钩子，disabled 时自动跳过，支持链式挂载 |
| `ProxyRule` | 真实 UDP/TCP socket 转发，含 backup_hosts 容错，失败回退原包 |

**功能开关（热切换，无需重启）：**

```
firewall / traffic_shaping / protocol_conversion / middleware / proxy
```

**防火墙规则持久化：**  
支持将 `FirewallRule` 列表序列化为 JSON 文件（`data/port_forwarder_firewall.json`），`auto_load()` 时自动加载，`close()` 时自动保存。

**新增 CLI 命令（在父类 5 个基础上增加 9 个）：**

| 命令 | 说明 |
|------|------|
| `features` | 列出所有功能开关状态 |
| `feature-enable <name>` | 启用指定功能 |
| `feature-disable <name>` | 禁用指定功能 |
| `firewall-list` | 列出所有防火墙规则 |
| `firewall-add` | 添加防火墙规则 |
| `firewall-remove <name>` | 删除防火墙规则 |
| `shaper-add` | 添加流量整形器 |
| `shaper-list` | 列出所有整形器 |
| `middleware-list` | 列出所有 middleware |

**新增统计字段（`get_stats()` / `handle_stats()`）：**

```
allowed_packets / denied_packets / converted_packets /
proxied_packets / shaped_dropped_packets / middleware_executed
```

---

## 问题修复

### BUG-1：`_hijacked_dispatch` 中的阻塞 `time.sleep`

**旧行为**：当流量整形器触发限速时，旧代码在 dispatch 线程中调用 `time.sleep(wait_time)`，阻塞整个转发线程，严重影响吞吐量。  
**修复**：`apply_traffic_shaping()` 改为立即返回 `wait_time`（> 0 表示需要限速），`_hijacked_dispatch` 检测到正值后立即返回 `False`，`shaped_dropped_packets` 计数递增，不再阻塞。

### BUG-2：`ProxyRule.forward()` 的占位符实现

**旧行为**：`forward()` 方法仅包含 `response = packet  # 占位符`，根本未建立网络连接，所谓的"代理转发"实际上什么都没做。  
**修复**：`_forward_udp()` 使用 `socket.SOCK_DGRAM`，`_forward_tcp()` 使用 `socket.SOCK_STREAM`，`forward()` 先尝试主机，失败后依次尝试 `backup_hosts`，全部失败才回退原包。

### BUG-3：`EnhancedPortForwarder` 为独立类，未继承 `PortForwarder`

**旧行为**：`class EnhancedPortForwarder:` 为独立类，自行重复实现了 `_lock`、`rule_sets`、`stats` 等字段，无法接受真实 `OpenSynaptic` 节点，也无法使用父类的规则集路由逻辑。  
**修复**：改为 `class EnhancedPortForwarder(PortForwarder):`，调用 `super().__init__(node, **kwargs)`，完全复用父类的规则集管理、dispatch 劫持机制、生命周期回调（`auto_load`/`close`）和 CLI 命令注册。

---

## 接口变更

### `__init__.py` 新增导出

```python
# v1.3.x 仅导出：
from opensynaptic.services.port_forwarder import PortForwarder, ForwardingRule, ForwardingRuleSet

# v1.4.0 新增导出：
from opensynaptic.services.port_forwarder import (
    EnhancedPortForwarder, FirewallRule, TrafficShaper,
    ProtocolConverter, Middleware, ProxyRule
)
```

### `get_required_config()` 新增 key

相比父类，`EnhancedPortForwarder.get_required_config()` 新增以下配置项：

```python
{
    "firewall_enabled":             True,
    "traffic_shaping_enabled":      True,
    "protocol_conversion_enabled":  True,
    "middleware_enabled":           True,
    "proxy_enabled":                True,
    "firewall_rules_file":         "data/port_forwarder_firewall.json",
}
```

---

## 测试

### Suite G（新增，35 项）

在 `scripts/exhaustive_plugin_test.py` 中新增 Suite G，覆盖所有新增组件：

| 子套件 | 项数 | 内容 |
|--------|------|------|
| G1 FirewallRule | 8 | 协议/IP/端口/包大小过滤，to_dict/from_dict，disabled 跳过 |
| G2 TrafficShaper | 6 | allow/drop/refill，wait_time 无副作用，非阻塞验证，disabled |
| G3 ProtocolConverter | 4 | passthrough，transform_func，计数统计，disabled |
| G4 Middleware | 5 | before/after 钩子，disabled，链式执行，全局开关 |
| G5 ProxyRule | 5 | fallback，request_count，backup_hosts，disabled，真实 UDP echo |
| G6 EPF pipeline | 10 | 继承检查，初始化，统计字段，热切换，配置，CLI，阻断，drop，全流水线，close |
| G7 持久化 | 2 | save+load 往返，persist=False 跳过写文件 || **合计** | **40** | |
### `scripts/enhanced_port_forwarder_check.py`（新增，10 项）

快速冒烟测试脚本，可在完整 Suite 之前单独运行验证核心路径。

```bash
python scripts/enhanced_port_forwarder_check.py
```

---

## 升级说明

本版本向后兼容。原有使用 `PortForwarder` 的代码无需任何修改。  
若需使用增强功能，将实例化替换为 `EnhancedPortForwarder` 即可：

```python
# 升级前
from opensynaptic.services.port_forwarder import PortForwarder
pf = PortForwarder(node=my_node)

# 升级后（完全向后兼容，直接替换）
from opensynaptic.services.port_forwarder import EnhancedPortForwarder
pf = EnhancedPortForwarder(node=my_node)
```

---

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/opensynaptic/services/port_forwarder/enhanced.py` | 重写 | 820 行，完整重写，修复3个阻塞缺陷 |
| `src/opensynaptic/services/port_forwarder/__init__.py` | 更新 | 新增 6 个符号导出 |
| `pyproject.toml` | 更新 | `version = "1.4.0"` |
| `scripts/exhaustive_plugin_test.py` | 更新 | 新增 Suite G（35 项） |
| `scripts/enhanced_port_forwarder_check.py` | 新增 | 新建 10 项冒烟测试脚本 |
| `TEST_COVERAGE.md` | 更新 | 反映 Suite G 和新脚本 |
| `RELEASE_NOTES_v1.4.0.md` | 新增 | 本文件 |
