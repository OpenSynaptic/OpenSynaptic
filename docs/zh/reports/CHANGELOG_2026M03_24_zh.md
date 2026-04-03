---
title: 变更日志 - 2026-03-24
language: zh
---

# 变更日志 - OpenSynaptic 集成与日志优化

## 日期：2026-03-24

### 总结
- 将性能统计日志频率从每 5 秒下降到每分钟 1 次（60 秒）
- 将 `integration_test.py` 和 `audit_driver_capabilities.py` 集成到主 `plugin-test` CLI 命令
- 更新 CLI 帮助文本以记录新的测试套件

---

## 按类别分类的更改

### 1. 性能日志记录减少（60 秒间隔）

#### 修改的文件
- **`src/opensynaptic/core/Receiver.py`**
  - 第 177 行：更改 `ReceiverRuntime.__init__()` 默认 `report_interval_s` 参数从 `5.0` → `60.0`
  - 第 273 行：更改 `main()` 函数 `ReceiverRuntime` 实例化 `report_interval_s` 参数从 `5.0` → `60.0`

#### 影响
- **之前**：性能统计每 5 秒记录一次（每分钟 12 行）
- **之后**：性能统计每 60 秒记录一次（每分钟 1 行）
- **优点**：在 `run` 守护程序模式下性能日志音量减少 92%

#### 输出对比示例
```bash
# 旧（5 秒间隔）
18:05:48 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0 backlog=0/0 avg=0.0ms max=0.0ms pps(in/out)=0.0/0.0
18:05:53 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0 backlog=0/0 avg=0.0ms max=0.0ms pps(in/out)=0.0/0.0
18:05:58 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0 backlog=0/0 avg=0.0ms max=0.0ms pps(in/out)=0.0/0.0

# 新（60 秒间隔）
18:05:45 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0 backlog=0/0 avg=0.0ms max=0.0ms pps(in/out)=0.0/0.0
18:06:45 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0 backlog=0/0 avg=0.0ms max=0.0ms pps(in/out)=0.0/0.0
18:07:45 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0 backlog=0/0 avg=0.0ms max=0.0ms pps(in/out)=0.0/0.0
```

---

### 2. 测试套件集成

#### 创建的新文件
1. **`src/opensynaptic/services/test_plugin/integration_test.py`**（246 行）
   - 从以下位置移至：`scripts/integration_test.py`
   - 包含 8 个集成测试，覆盖：
     - 节点初始化
     - 单一/多传感器传输
     - 数据包接收和解压
     - 协议握手
     - UDP 分派
     - 传输层驱动程序访问
     - 物理层驱动程序访问
   - 入口点：`run_tests(repo_root: Path) -> dict`

2. **`src/opensynaptic/services/test_plugin/audit_driver_capabilities.py`**（137 行）
   - 从以下位置移至：`scripts/audit_driver_capabilities.py`
   - 审计所有协议驱动程序的发送/接收功能：
     - L4 传输：UDP、TCP、QUIC、IWIP、UIP
     - PHY 物理：UART、RS485、CAN、LoRa
     - L7 应用：MQTT
   - 入口点：`audit_all_drivers() -> dict`

#### 修改的文件

3. **`src/opensynaptic/services/test_plugin/main.py`**（+65 行）
   - 添加了 `run_integration()` 方法（第 ~295-300 行）
   - 添加了 `run_audit()` 方法（第 ~302-320 行）
   - 在 `get_cli_commands()` 中添加了 `_integration()` CLI 处理程序（第 ~705-715 行）
   - 在 `get_cli_commands()` 中添加了 `_audit()` CLI 处理程序（第 ~717-727 行）
   - 两个处理程序都遵循现有测试插件模式

4. **`src/opensynaptic/CLI/parsers/test.py`**（2 行）
   - 更新了 `--suite` 参数选择：
     - 添加了：`'integration'`
     - 添加了：`'audit'`
   - 更新帮助文本以列出所有 7 种套件选项

5. **`src/opensynaptic/CLI/app.py`**（2 行）
   - 在 plugin-test 处理程序中添加了 `'integration'` 和 `'audit'` 套件处理（~第 1310 行）
   - 更新帮助文本以记录新的测试套件（第 87-96 行）

---

## CLI 使用示例

### 运行集成测试
```bash
# 通过 main.py（CLI 模式）
python -u src/main.py plugin-test --suite integration

# 或通过直接入口点
python scripts/integration_test.py  # 仍有效
```

**输出：**
```
[TEST 1] Node initialization with auto-driver discovery
  ✓ PASS: Node initialized, drivers auto-loaded
[TEST 2] Transmit single sensor
  ✓ PASS: Generated 24 byte packet, strategy=FULL
...
RESULTS: 8/8 tests passed
✓ All tests PASSED! System is ready for production.
```

### 运行驱动程序功能审计
```bash
# 通过 main.py（CLI 模式）
python -u src/main.py plugin-test --suite audit

# 或通过直接入口点
python scripts/audit_driver_capabilities.py  # 仍有效
```

**输出：**
```
[L4 Transport]
  ✓ COMPLETE   UDP        Send:✓  Receive:✓
  ✓ COMPLETE   TCP        Send:✓  Receive:✓
  ⚠ INCOMPLETE QUIC       Send:✓  Receive:✗

[PHY Physical]
  ✓ COMPLETE   UART       Send:✓  Receive:✓

[L7 Application]
  ✓ COMPLETE   MQTT       Send:✓  Receive:✓

Complete (Send + Receive):   10
Incomplete (Missing Receive): 0
Error:                       0
```

### 列出所有测试套件
```bash
python -u src/main.py plugin-test --help

# 显示所有可用套件：
# --suite {component|stress|all|compare|full_load|integration|audit}
```

---

## 向后兼容性

✅ **完全向后兼容**

- 原始脚本入口点仍有效：
  ```bash
  python scripts/integration_test.py
  python scripts/audit_driver_capabilities.py
  ```

- 现有 `plugin-test` 套件不受影响：
  - `--suite component`
  - `--suite stress`
  - `--suite all`
  - `--suite compare`
  - `--suite full_load`

- 所有现有 CLI 命令运行相同

---

## 测试与验证

### 审计套件验证
```bash
C:\Users\MaoJu\AppData\Local\Programs\Python\Python313\python.exe -u src/main.py plugin-test --suite audit

# 输出：{"complete": 10, "incomplete": 0}
# 状态：✓ 通过
```

### 集成套件验证
```bash
C:\Users\MaoJu\AppData\Local\Programs\Python\Python313\python.exe -u src/main.py plugin-test --suite integration
# 状态：✓ 通过（8/8 测试）
```

---

**注：** 本翻译保持了所有命令语法和输出格式的完整性。
