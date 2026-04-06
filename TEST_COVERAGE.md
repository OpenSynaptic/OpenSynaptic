# OpenSynaptic 测试覆盖说明

> 最后更新：2026-04-07（正交测试新增）

---

## 总览

| 层级 | 脚本/文件 | 测试项数 | 最近结果 |
|------|-----------|----------|----------|
| Unit Tests (pytest) | `tests/unit/test_core_algorithms.py` | 3 | ✅ PASS |
| Unit Tests (pytest) | `tests/unit/test_textual_tui.py` | 5 | ✅ PASS |
| Integration Tests (pytest) | `tests/integration/test_pipeline_e2e.py` | 1 | ✅ PASS |
| Integration Script | `scripts/integration_test.py` | 9 | ✅ 9/9 PASS |
| Business Logic Script | `scripts/exhaustive_business_logic.py` | 985 | ✅ 983/985 (2 SKIP) |
| Plugin Exhaustive Script | `scripts/exhaustive_plugin_test.py` | 205 | ✅ 205/205 PASS |
| Security Infra Script | `scripts/exhaustive_security_infra_test.py` | 43 | ✅ 43/43 PASS |
| Orthogonal Design Script | `scripts/exhaustive_orthogonal_test.py` | 24 | ✅ 24/24 PASS |

---

## 一、单元测试（pytest）

运行命令：
```bash
pytest tests/ -v
```

### 1.1 `tests/unit/test_core_algorithms.py`

针对底层算法的正确性验证，依赖 native C 库（`os_base62`、`os_security`），库不可用时自动 SKIP。

| 测试函数 | 内容 |
|----------|------|
| `test_crc16_reference_vector` | 验证 CRC-16/CCITT 算法：已知输入 `"123456789"` → 期望校验值 `0x29B1` |
| `test_base62_compress_decompress_roundtrip` | 单条 fact（`Pa` 单位，101.3）经 `engine.compress()` → `engine.decompress()` 后字段完整还原，数值误差 < 0.1% |
| `test_packet_encode_decode_roundtrip` | fact（湿度 `%`，56.1）经 `compress` → `fusion.run_engine(FULL)` → `fusion.decompress` 完整还原，验证设备 ID 和传感器 ID 字段 |

### 1.2 `tests/unit/test_textual_tui.py`

TUI 服务模块的单元测试，全程使用 `MockNode` 不依赖真实硬件。

| 测试函数 | 内容 |
|----------|------|
| `test_tui_service_import` | `TUIService` 可正常导入 |
| `test_tui_render_section` | `render_section('identity')` 返回包含 `device_id` 字段的 dict |
| `test_tui_render_text` | `render_text(['identity'])` 返回合法 JSON，含 `identity` 和 `timestamp` key |
| `test_tui_cli_commands` | `get_cli_commands()` 包含 `render`、`interactive`、`bios`、`dashboard` |
| `test_widget_imports` | 所有 TUI Widget 模块（`BaseTUIPanel`、`IdentityPanel`、`ConfigPanel` 等）可正常导入 |

### 1.3 `tests/integration/test_pipeline_e2e.py`

端到端集成测试（pytest 管理），使用真实 `OpenSynaptic` 节点。

| 测试函数 | 内容 |
|----------|------|
| `test_virtual_sensor_to_receive_roundtrip` | 2 路传感器（`Pa`、`%`）`transmit` → `receive` 完整链路；校验 packet 类型、aid 类型、strategy 合法性、decoded 字段完整性 |

---

## 二、集成测试脚本

### 2.1 `scripts/integration_test.py`（9 项）

独立 Python 脚本，验证节点各层级功能的基础行为。使用隔离临时目录（registry、session、id_allocation 均独立）。

运行命令：
```bash
python scripts/integration_test.py
```

| # | 测试名称 | 验证内容 |
|---|----------|----------|
| 1 | **节点初始化** | `OpenSynaptic` 初始化完成；`assigned_id` 非空；驱动自动发现（TransportManager 加载 > 0 个 adapter） |
| 2 | **单传感器发送** | `transmit(sensors=[["sensor1","OK",42.0,"Pa"]])` 返回非空 bytes packet，`strategy` 为合法字符串 |
| 3 | **多传感器发送** | 3 路传感器（`Pa`、`Cel`、`%`）打包进单个 packet，验证 `len(packet) > 0` |
| 4 | **接收与解压** | 手工构造 FULL packet，`node.receive()` 返回 dict，含 `id` 字段，无 `error` |
| 5 | **协议层接收** | `receive_via_protocol(packet, addr)` 返回 `{'type': 'DATA'/'CTRL'/'ERROR', ...}` |
| 6 | **UDP 派发** | `dispatch(pkt, medium='UDP')` 能正常调用 UDP 驱动（UDP 无服务端时结果也记为 PASS） |
| 7 | **传输层驱动访问** | `get_transport_layer_manager()` 加载 `udp` adapter，含 `send` 方法 |
| 8 | **物理层驱动访问** | `get_physical_layer_manager()` 加载 `uart` adapter，含 `send` 方法 |
| 9 | *(Test 4 计数修复导致的计数项)* | — |

> **注**：Test 4 中存在一处 `tests_passed += 1` 重复计数，最终显示 9/9，实为 8 个逻辑测试。

---

## 三、穷举式业务逻辑测试

### 3.0 `scripts/exhaustive_business_logic.py`（914 项）

对协议全链路进行系统性穷举测试，涵盖单位、传感器通道组合、状态编码、策略切换和批量 API 五个维度。所有套件共享一个隔离节点实例（temp dir 独立），耗时约 500~600ms。

运行命令：
```bash
python scripts/exhaustive_business_logic.py
```

最终结果（2026-04-06）：

```
套件                              总计   通过   失败   跳过
A | 每单位全链路边界值              494    492      0      2
B | 多传感器跨类组合                350    350      0      0
C | 状态字穷举矩阵                   56     56      0      0
D | FULL→DIFF 策略递进               9      9      0      0
E | 批量发送等价性                    5      5      0      0
总计                               914    912      0      2
通过率: 100.0%  耗时: ~545ms
```

---

#### Suite A — 每单位全链路边界值（494 项）

**链路**：`node.transmit()` → `node.receive()` → 数值还原校验

对 `libraries/Units/` 下全部 15 个单位库中每个 UCUM 单位，测试下列边界值（未特殊配置的单位取通用值 `[0.0, 1e-5, 1.0, 1e6]`）：

| 单位 | 测试值 |
|------|--------|
| `K` | 0, 1e-5, 273.15, 373.15, 5778 |
| `Cel` | −273, 0, 25, 100, 5504.85 |
| `degF` | −459, 32, 77, 212 |
| `Pa` | 0, 1e-5, 101325, 1e7 |
| `bar` | 0, 1e-7, 1.01325, 1000 |
| `psi` | 0, 1e-5, 14.696, 1e5 |
| `m / kg / s / A / cd / Hz / bit / By` | 各 4 个边界值 |
| `mol` | 0, 1e-15, 1, **6.022e23 (SKIP)** |
| 其余单位 | 通用 4 值 |

**通过条件**：解码值与标准化后期望值误差 ≤ 0.1%（相对）或 0.001（绝对）。  
**SKIP 条件**：标准化后绝对值超出 base62 int64 有效表示范围（`|std_val| > 9.22×10¹⁴`）。

> 2 个 SKIP 项：`mol=6.022e+23`、`AU=1e+06` — 天文量级值超出编码器 `c_longlong × precision=4` 上限，属已知硬件设计决策，不计失败。

---

#### Suite B — 多传感器跨类别组合包（350 项）

从 15 个单位库各取一个代表单位，枚举 **2 ~ 8 通道**所有 C(N, k) 组合（每种通道数最多取 50 组），发送后验证解码包可成功解析。

| 通道数 | 组合规模 | 验证内容 |
|--------|----------|----------|
| 2 通道 | C(15,2) = 105 组 → 取 50 | packet 非空，`receive()` 返回无 error 的 dict |
| 3 通道 | C(15,3) = 455 组 → 取 50 | 同上 |
| 4 通道 | C(15,4) = 1365 组 → 取 50 | 同上 |
| 5 ~ 8 通道 | 各取 50 | 同上 |

---

#### Suite C — 状态字穷举矩阵（56 项）

穷举所有 7 × 8 = **56 种设备状态 × 传感器状态** 组合，验证编解码不报错。

| 设备状态（7） | 传感器状态（8） |
|--------------|----------------|
| ONLINE / OFFLINE / WARN / ERROR / STANDBY / BOOT / MAINT | OK / WARN / ERR / FAULT / N/A / OFFLINE / OOL / TEST |

---

#### Suite D — FULL → DIFF 策略递进与一致性（9 项）

对同一设备 ID 连续发送 8 轮（温度值每轮 +0.5°C），验证策略切换行为与数值一致性。

| 轮次 | 期望策略 | 验证内容 |
|------|----------|----------|
| 前 `target_sync_count (=3)` 轮 | `FULL_PACKET` | 收发数值一致 |
| 之后各轮 | `DIFF_PACKET` | 收发数值一致，与 FULL 轮一致 |
| 汇总检查（+1项） | 至少出现过 DIFF | 或模板已缓存（全程 DIFF 也合法） |

---

#### Suite E — transmit_batch 批量发送等价性（5 项）

| 项 | 内容 |
|----|------|
| batch 返回数 | `transmit_batch()` 返回 4 个结果（与输入条目数一致） |
| DEVTESTE1 ~ E4 | 各条目 packet 字节数 > 0，可独立解码 |

---

---

## 三点五、Suite F：SI 前缀单位全链路穷举（新增）

`scripts/exhaustive_business_logic.py`中新增 Suite F，覆盖了此前完全空白的前缀展开逻辑（即 `standardization.py` 中 `_resolve_unit_law()` 的前缀匹配分支）。

**测试结果（2026-04-06）：**

```
F1 十进制前缀  60 tests: 60 pass, 0 fail, 0 skip
F2 二进制前缀   5 tests:  5 pass, 0 fail, 0 skip
F3 拒绝测试     6 tests:  6 pass, 0 fail, 0 skip
```

#### Suite F1 — 十进制前缀 × 前缀感知单位（60 项）

6 个代表性前缀（`G/M/k/m/u/n`）× 11 个基础单位（`Hz/By/bit/m/g/Pa/W/V/A/J/s`）全组合，对每一项执行：
1. `node.transmit(sensors=[\["S1", "OK", 1.0, "kHz"\]])` 发送带前缀单位的数据包
2. `node.receive(pkt)` 解码，取出 `s1_v`
3. 验证 `s1_v == 1.0 × prefix_factor × unit_factor + offset`（容差 0.1%）
4. 如果标准化后的值超出 Base62 int64 编码上限 ≈ 9.22×10¹⁴，标记为 SKIP

#### Suite F2 — 二进制前缀 × 信息学单位（5 项）

| 前缀单位 | 等价标准化量 | 验证结果 |
|------|------|------|
| `KiBy` | 1 KiB = 1×1024×8 = 8192 bits | recv=8192.0 ✅ |
| `MiBy` | 1 MiB = 1×1048576×8 = 8388608 bits | recv=8388608.0 ✅ |
| `GiBy` | 1 GiB = 1×1073741824×8 = 8589934592 bits | recv=8589934592.0 ✅ |
| `Kibit` | 1 Kibit = 1024 bits | recv=1024.0 ✅ |
| `Mibit` | 1 Mibit = 1048576 bits | recv=1048576.0 ✅ |

#### Suite F3 — `can_take_prefix=False` 单位被正确拒绝（6 项）

对 `count/cmd/rst/stp/cmdA/cmdB` 等 `can_take_prefix=False` 的单位加前缀后发送，验证：
- `_resolve_unit_law("kcount")` 返回 None（匹配失败）
- 传感器被标准化引擎静默丢弃——返回包中无 `s1_v` 字段

---

## 四、插件穷举测试

### 4.0 `scripts/exhaustive_plugin_test.py`（205 项）

对所有服务插件进行最严格的逐接口穷举，覆盖对象模型、生命周期、边界值、并发安全和注册表全集。

运行命令：
```bash
python scripts/exhaustive_plugin_test.py
```

最终结果（2026-04-06）：

```
套件                                   总计   通过   失败   跳过
A | DatabaseManager (SQLite)             14     14      0      0
B | PortForwarder 规则+生命周期         107    107      0      0
C | TestPlugin 组件套件                    4      4      0      0
D | DisplayAPI 全格式穷举                44     44      0      0
E | Plugin 注册表                         36     36      0      0
总计                                    205    205      0      0
通过率: 100.0%  耗时: ~4900ms
```

---

#### Suite A — DatabaseManager (SQLite) 穷举（14 项）

| # | 测试内容 |
|---|----------|
| A1 | `connect()` + `ensure_schema()`：`_ready` 置 True |
| A2 | 4 种有代表性的 fact（单传感器 / 双传感器 / 无传感器 / 8 通道）逐条 `export_fact()` 返回 True |
| A3 | 3 种无效输入（`None`、`{}`、非 dict 字符串）→ `export_fact()` 返回 False |
| A3b | 最小合法 fact（空字段 dict）→ `export_fact()` 返回 True |
| A4 | `export_many(4 facts)` 批量导出 → 返回 4 |
| A5 | `export_many([])` → 返回 0 |
| A6 | 8 线程并发 `export_fact()`，无竞争异常 |
| A7 | `close()` → `_ready=False`，re-`connect()` → `_ready=True` |
| A8 | `from_opensynaptic_config(sql.enabled=False)` → `None` |
| A9 | `from_opensynaptic_config(sql.enabled=True)` → `DatabaseManager` 实例 |

---

#### Suite B — PortForwarder 规则模型 + 生命周期（107 项）

| # | 测试内容 |
|---|----------|
| B1 | 所有合法协议对：10×10=100 种 `(from_protocol, to_protocol)` 组合均可创建 `ForwardingRule` |
| B2 | 4 种非法协议名（`HTTP`、`FTP`、`""`、`"  "`）→ 必须抛出 `ValueError` |
| B3 | `ForwardingRule.to_dict()` / `from_dict()` 往返，所有字段（含 priority、enabled、from_port）无损 |
| B4 | `ForwardingRuleSet.add_rule/remove_rule/get_rules_sorted`：优先级降序正确 |
| B5 | `ForwardingRuleSet.to_dict()` / `from_dict()` 往返 |
| B6 | `PortForwarder(node=None)` 初始化 + `close()`，无崩溃 |
| B7 | 真实节点完整生命周期：`auto_load()` 劫持 dispatch → `is_hijacked=True` → `close()` 恢复 dispatch |
| B8 | `get_required_config()` 结构合法（含 `enabled`、`rule_sets`） |

---

#### Suite C — TestPlugin 组件套件（4 项）

| # | 测试内容 |
|---|----------|
| C1 | `build_suite()` 可调用，返回 133 个 `TestCase` |
| C2 | 所有 `TestCase` 类名可枚举 |
| C3 | 运行全部非 rscore 组件测试（112 tests）：0 fail、0 error（rscore Rust 后端测试在无 native 环境时跳过） |
| C4 | `TestPlugin(node=None)` 初始化 + `get_required_config()` 结构合法 |

---

#### Suite D — DisplayAPI + BuiltinDisplayProviders（44 项）

| # | 测试内容 |
|---|----------|
| D1 | 6 个内建 section（`identity/config/transport/pipeline/plugins/db`）均已注册到 `DisplayRegistry` |
| D2 | 6 sections × 5 formats（`json/html/text/table/tree`）= 30 次全格式渲染，每次验证返回类型 |
| D3 | `register` → 重复注册返回 `False` → `unregister` → 二次注销返回 `False` → re-register 成功 |
| D4 | `list_by_category('core')` → 返回 ≥6 个内建 provider |
| D5 | `supports_format()` 对所有 `DisplayFormat` 枚举值（5 个）均返回 `True` |
| D6 | 20 线程并发 `register()`，无竞争异常 |

---

#### Suite E — Plugin 注册表（36 项）

对所有 6 个注册表插件（`tui`、`test_plugin`、`web_user`、`dependency_manager`、`env_guard`、`port_forwarder`）各执行 6 项检查：

| 检查 | 内容 |
|------|------|
| E/\<plugin\>/spec | `PLUGIN_SPECS` 包含该插件条目 |
| E/\<plugin\>/import | 模块可正常 `importlib.import_module()` |
| E/\<plugin\>/class | 对应类名可 `getattr()` 且 callable |
| E/\<plugin\>/config | `get_required_config()` 返回含 `enabled` 的合法 dict |
| E/\<plugin\>/nodenil | `cls(node=None)` 初始化 + `close()` 无崩溃 |
| E/\<plugin\>/defaults | `defaults` 字典含 `enabled` 字段 |

---

## 五、CLI 穷举测试（已有，非新增）

### 5.1 `scripts/cli_exhaustive_check.py`（41 项）

通过 `subprocess` 调用 `src/main.py`，覆盖所有 CLI 命令。

→ 详见 [CLI 测试列表](#21-scriptsintegration_testpy9-项)（集成脚本章节中已说明）

### 5.2 `scripts/services_smoke_check.py`（16 项）

覆盖 `tui/web_user/dependency_manager/env_guard/test_plugin/port_forwarder` 的 CLI 子命令冒烟。

---

## 六、安全基础设施穷举测试（新增）

### 6a. `scripts/exhaustive_security_infra_test.py`（43 项）

覆盖此前零覆盖的 4 个核心基础设施模块，**含随机 ID 分配专项测试**。

---

#### Suite A — IDAllocator 随机 ID 分配 + 租约穷举（13 项）

| # | 测试内容 |
|---|---------|
| A1 | 顺序分配 200 个 ID，全部唯一，范围在 `[1, 9999]` 内 |
| A2 | 随机种子 500 次分配（含设备去重），唯一 ID 数量合理 |
| A3 | 同 `device_id` 两次分配 → 复用同一 ID；不同 `device_id` → 不同 ID |
| A4 | `release_id(immediate=True)` 内部自动回收，`is_allocated` 立即为 False，下次分配复用该 ID |
| A5 | `allocate_pool(50)` → 50 个唯一 ID |
| A6 | `release_pool(10, immediate=True)` → 返回计数 10 |
| A7 | `touch(aid)` 刷新 `lease_expires_at`，state 保持 active |
| A8 | `is_allocated` / `get_meta` 对已分配/未分配 ID 正确返回 |
| A9 | `stats()` 含全部必需字段（total_allocated、released、range、lease_metrics） |
| A10 | 20 线程并发 `allocate_id` → 0 重复、0 异常 |
| A11 | 自适应速率：`high_rate_threshold_per_hour=1.0`，5 次分配后 `rate` 字段为数值 |
| A12 | 持久化往返：重建 `IDAllocator` 后已分配 ID 仍保留，设备去重仍有效 |
| A13 | 池耗尽（end_id - start_id = 2）后第 4 次分配抛出 `RuntimeError` |

---

#### Suite B — OSHandshakeManager 握手状态机（12 项）

| # | 测试内容 |
|---|---------|
| B1 | 初始状态：`has_secure_dict=False`，`should_encrypt_outbound=False`，`get_session_key=None` |
| B2 | `note_local_plaintext_sent` → `state=PLAINTEXT_SENT`，`pending_key` 已派生 |
| B3 | `establish_remote_plaintext` → `state=DICT_READY`，`key` 派生为 bytes，`has_secure_dict=True` |
| B4 | `confirm_secure_dict` 通过 `pending_key` 路径 → True，key 与 `derive_session_key(aid, ts)` 一致 |
| B5 | `mark_secure_channel` → `state=SECURE`，`decrypt_confirmed=True`，`should_encrypt_outbound=True` |
| B6 | 5 个不同 AID 均完成 INIT→SECURE 完整跃迁 |
| B7 | `classify_and_dispatch`：空包→`ERROR`，未知 CMD 0xFF→`UNKNOWN` |
| B8 | `classify_and_dispatch`：`CMD.PING` → `type=CTRL`，响应为 PONG 包 |
| B9 | `device_role=tx_only`：入向 `DATA_FULL` → `type=IGNORED` |
| B10 | `secure_sessions.json` 持久化往返：重建后 `get_session_key` 返回相同 bytes |
| B11 | `note_server_time(0)` 被忽略；`note_server_time(1.7e9)` 被接受 |
| B12 | 挂载 `IDAllocator` 后 `ID_REQUEST` → 响应 `ID_ASSIGN`，cmd 字节正确 |

---

#### Suite C — EnvironmentGuardService 逻辑（8 项）

| # | 测试内容 |
|---|---------|
| C1 | `get_required_config()` 含全部必需字段 |
| C2 | `ensure_resource_library(force_reset=True)` 写出 JSON 文件，含 `resources` dict |
| C3 | `_on_error(EnvironmentMissingError event)` → `_issues` 新增 1 条，含 `environment`、`ts` 字段 |
| C4 | `max_history=5`，注入 10 个错误 → `_issues` 精确截断到 5 条 |
| C5 | `_status_payload()` 含 `ok/service/issues_total/attempts_total/resource_summary` |
| C6 | `_write_status_json` + `_load_state_from_status_json` 往返，issues 正确还原 |
| C7 | `_resolve_resource_entry('native_library','os_base62')` 命中默认库；未知种类返回空 dict |
| C8 | `auto_load()` → `_initialized=True`；`close()` → `_initialized=False` |

---

#### Suite D — EnhancedPortForwarder 全组件（10 项）

| # | 测试内容 |
|---|---------|
| D1 | 构造函数 + `get_required_config()` 结构合法，`is_hijacked=False` |
| D2 | 5 个功能开关（firewall/traffic_shaping/protocol_conversion/middleware/proxy）`enable/disable/toggle` 均正确 |
| D3 | 防火墙 deny UDP 规则 → `check_firewall` 返回 False；TCP 无规则 → True |
| D4 | 高优先级 allow(p=10) > 低优先级 deny(p=1)：UDP 放行，TCP 阻断 |
| D5 | 令牌桶 TrafficShaper：burst_capacity=500，发 500B→True，再发 1B→False，`get_wait_time>0` |
| D6 | `traffic_shaping_enabled=False` → `apply_traffic_shaping` 返回 0.0 |
| D7 | 自定义 `transform_func` 被调用；无匹配转换器原包透传 |
| D8 | Middleware `before_dispatch`/`after_dispatch` 钩子按顺序执行，返回值传递正确 |
| D9 | 真实 `OpenSynaptic` 节点挂载：`auto_load` → dispatch 被劫持；`transmit+dispatch` 触发统计 `total_packets≥1`；`close` 还原 |
| D10 | `get_stats()` 含全部统计字段 |

---

## 八、正交测试（新增）

### 8a. `scripts/exhaustive_orthogonal_test.py`（24 项）

系统性验证多子系统交互行为，与穷举测试互补。

---

#### Suite EP — EnhancedPortForwarder 5 个二値功能开关 L8 正交（8 runs）

**设计目标**：验证 firewall / traffic_shaping / protocol_conversion / middleware / proxy 之间任意两两组合时的交互行为符合预期，尤其是“firewall 阻断后其他步骤不再执行”这一限制在所有涉及 firewall 的组合下均被验证。

| Run | fw | ts | pc | mw | px | 验证重点 |
|-----|----|----|----|----|----|---------|
| EP-0 | OFF | OFF | OFF | OFF | OFF | 全 disabled: 所有统计=0 |
| EP-1 | OFF | OFF | OFF | ON  | ON  | middleware 前后钩子均执行 |
| EP-2 | OFF | ON  | ON  | OFF | OFF | 整形 + 转换均生效 |
| EP-3 | OFF | ON  | ON  | ON  | ON  | 全 enabled + fw=OFF: 所有步骤执行 |
| EP-4 | ON  | OFF | ON  | OFF | ON  | fw 阻断，转换不运行，代理不运行 |
| EP-5 | ON  | OFF | ON  | ON  | OFF | **mw×fw 关键交互：before 执行，after 不执行** |
| EP-6 | ON  | ON  | OFF | OFF | ON  | fw 阻断，整形不运行 |
| EP-7 | ON  | ON  | OFF | ON  | OFF | **mw×fw 关键交互：before 执行，after 不执行** |

**发现的关键交互**：`middleware.before_dispatch` 在防火墙检查之前执行（无论防火墙是否启用），而 `middleware.after_dispatch` 仅在防火墙放行时执行——这个不对称行为在 EP-5、EP-7 run 中被明确验证。

---

#### Suite XC — IDAllocator×Unit×Medium×ChannelCount L16 正交（16 runs）

**设计目标**：验证跨层链路耦合：设备 Key 类型影响 ID 分配的正确性、单位类型影响编解码、发送媒介影响 dispatch、通道数影响包结构，四者两两组合均被覆盖。

| 因子 | 级别 | 内容 |
|--------|------|---------|
| **A**: 设备 Key 类型 | 4 | `device_id` / `mac` / `serial` / `uuid` |
| **B**: 单位类型 | 4 | `Pa`（压力）/ `Cel`（温度）/ `Hz`（频率）/ `By`（字节）|
| **C**: 发送媒介 | 4 | `UDP` / `TCP` / `UART` / `CAN` |
| **D**: 通道数 | 4 | 1 / 2 / 3 / 4 |

每个 run 验证三个子链路：
1. **IDAllocator 子测试** — 用 Key 类型 A 分配 D 个设备 ID，全部唯一，meta 字段匹配
2. **发送×接收子测试** — D 个通道加单位 B，`transmit`→`receive` 无错误，`s1_v` 数字合理
3. **ForwardingRule 子测试** — `ForwardingRule(from=C, to=C)` 构造、`to_dict`、`from_dict` 往返正确
4. **dispatch 子测试** — `node.dispatch(pkt, medium=C)` 不抛异常

---

## 七、已知限制


| 限制 | 说明 |
|------|------|
| base62 编码范围 | `Base62Codec` 使用 `c_longlong`（int64），`precision=4` 时有效值上限 ≈ **9.22×10¹⁴**。天文量级单位超出此范围，测试中标记为 SKIP。 |
| UDP dispatch 验证 | `integration_test.py` Test 6 仅验证驱动能被调用，不校验网络层投递成功。 |
| pytest Test 4 计数 | `integration_test.py` Test 4 中 `tests_passed += 1` 多计一次，最终显示 `9/9` 实为 8 个逻辑测试。 |
| TUI 测试隔离性 | `test_textual_tui.py` 全程使用 `MockNode`，不覆盖真实节点的 TUI 渲染路径。 |
| rscore 组件测试 | `TestRscoreFusionEngine` 等 rscore 专属测试类依赖 Rust native 库；无 native 环境时跳过，不算失败。 |
| MySQL/PostgreSQL | `db_engine` 仅测试 SQLite（`:memory:`），MySQL/PostgreSQL driver 未在 CI 中验证（需实际 DB 服务）。 |
