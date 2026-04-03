---
layout: default
title: OpenSynaptic 优雅重启指南
language: zh
---

# OpenSynaptic 优雅重启指南

**最后更新**：2026-04-03

---

## 概述

`os-node restart --graceful` 命令为 OpenSynaptic 运行循环提供了零停机时间重启机制。与强制停止（Ctrl+C）和手动重启不同，它编排优雅关闭和自动进程重生。

### 用例

- **原地进程重启**，无损协议连续性
- **配置重新加载**，改配置后（无损接收器状态）
- **调试工作流**，双终端模式（终端 A：运行循环；终端 B：控制命令）
- **生产发布**，最小化服务中断

---

## 快速开始

### 基本用法（10 秒优雅关闭）

```powershell
# 终端 A：启动运行循环
os-node run

# 终端 B：启动优雅重启
os-node restart --graceful
```

**发生的过程**：
1. 终端 B 广播重启信号
2. 当前运行进程在心跳 tick 期间收到消息
3. 等待最多 10 秒，让进行中的操作完成
4. 旧进程终止
5. 新运行进程在新终端中自动启动

### 自定义超时

```powershell
# 仅等待 5 秒后强制重启
os-node restart --graceful --timeout 5

# 等待 30 秒让缓慢操作完成
os-node restart --graceful --timeout 30
```

### 使用自定义主机/端口

```powershell
# 重启并使用自定义服务器进行 ID 分配
os-node restart --graceful --host 192.168.1.100 --port 9090

# 重启，使用特定超时和主机
os-node restart --graceful --timeout 15 --host 10.0.0.1 --port 8080
```

---

## 工作原理

### 架构

```
终端 A（运行进程）              终端 B（控制终端）
─────────────────────────       ──────────────────────────
  os-node run                     os-node restart --graceful
       ↓                                ↓
  [运行循环]                      [通过 subprocess 生成新运行]
  Tick 1  ✓                       
  Tick 2  ✓                       
  Tick 3  ← [等待 ~10s]           
  Tick 4 → [关闭完成]
       ↓
  [退出]
       
                                  新进程启动 →
                                  ↓
                                  [全新运行循环]
                                  Tick 1 ✓
```

### 执行流程

```
1. 用户运行：os-node restart --graceful --timeout 10

2. 系统操作：
   - 记录重启配置
   - 使用相同参数构建新的运行命令
   - 在后台生成新进程（Windows：新控制台窗口）
   - 打印说明到终端 B
   - 等待指定的超时时间
   - 将控制权返回给终端 B

3. 并行（在终端 A 中）：
   - 当前运行循环继续正常操作
   - 检测优雅关闭信号（如果已实现）
   - 刷新任何缓冲数据
   - 干净地终止
   - 终端关闭（或保持打开以查看日志）

4. 结果：
   - 新进程完全初始化
   - 协议状态已恢复
   - 无需手动干预
```

### 优雅 vs. 非优雅

| 方面 | 优雅 | 非优雅（当前） |
|------|------|---------------|
| **关闭信号** | 启动时广播 | N/A（未发送信号）|
| **进行中的操作** | 允许完成（达到超时） | 突然终止 |
| **状态保存** | Config.json 保留 | ✓ 保留 |
| **接收器清理** | 正确资源清理 | 可能泄漏（不太可能）|
| **超时窗口** | 可配置（默认 10s） | N/A |
| **用例** | 生产 / 长期会话 | 开发 / 快速重启 |

---

## 示例

### 开发工作流（双终端）

**终端 A**：
```powershell
cd "e:\新建文件夹 (2)"
.\run-main.cmd run
```

**终端 B**（做代码更改后）：
```powershell
cd "e:\新建文件夹 (2)"

# 检查当前状态
.\run-main.cmd status

# 做配置更改
.\run-main.cmd config-set --key engine_settings.precision --value 6 --type int

# 优雅重启以应用更改
.\run-main.cmd restart --graceful --timeout 5

# 观察新进程初始化
.\run-main.cmd status

# 检查终端 A 窗口中的日志
```

### 压力测试场景

```powershell
# 终端 A：启动压力测试
os-node plugin-test --suite stress --workers 8 --total 1000

# 终端 B：监控和优雅重启
os-node status
os-node restart --graceful --timeout 30  # 等待 30s 让批处理完成
os-node plugin-test --suite stress --workers 8 --total 1000  # 下一批
```

### 生产自动重启（脚本化）

```powershell
# 每小时自动重启一次
$interval = 3600  # 秒

while ($true) {
    Write-Host "[$(Get-Date)] 下一次重启在 $interval 秒后..."
    Start-Sleep -Seconds $interval
    
    Write-Host "[$(Get-Date)] 启动优雅重启..."
    & ".\run-main.cmd" restart --graceful --timeout 30
    
    Write-Host "[$(Get-Date)] 重启完成。等待稳定..."
    Start-Sleep -Seconds 10  # 等待新进程稳定
}
```

---

## 命令参考

### 参数

| 参数 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `--graceful` | 标志 | `true` | 启用优雅关闭模式（等待操作完成）|
| `--timeout` | 浮点数 | `10.0` | 重启前等待优雅关闭的秒数 |
| `--host` | 字符串 | `None` | 用于 ID 分配的服务器主机（省略时使用 Config）|
| `--port` | 整数 | `None` | 用于 ID 分配的服务器端口（省略时使用 Config）|
| `--config` | 路径 | `auto-detect` | Config.json 的路径 |

### 输出

命令返回用于脚本的 JSON 输出：

```json
{
  "action": "restart",
  "graceful": true,
  "timeout_seconds": 10.0,
  "new_run_command": "python.exe -m opensynaptic run",
  "timestamp": "2026-04-03 19:35:33"
}
```

成功启动后：

```json
{
  "restart_status": "complete",
  "new_pid": 12345,
  "timestamp": "2026-04-03 19:35:43"
}
```

---

## 别名

所有这些都是等价的：

```powershell
os-node restart
os-node os-restart
python -u src/main.py restart
.\run-main.cmd restart
```

---

## 故障排除

### "启动新运行进程失败"

**可能原因**：
- Python 解释器不在 PATH 中
- Config.json 无效/缺失
- 旧进程已占用端口
- 权限不足，无法生成子进程

**解决方案**：
```powershell
# 验证 Python 是否可访问
python --version

# 检查 Config.json 有效性
os-node config-show

# 检查端口冲突
Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue

# 手动回退：在终端 A 中按 Ctrl+C，然后重启
os-node run
```

### "新运行进程启动但不响应"

**可能原因**：
- 进程初始化超时
- 缺失所需模块（依赖问题）
- Config 语法错误
- 与旧进程的端口冲突

**解决方案**：
```powershell
# 检查进程是否仍在运行
Get-Process python | Where-Object {$_.Id -eq 12345}

# 检查新终端窗口中的日志或输出
os-node status

# 如需修复依赖项
os-node deps --cmd repair

# 必要时硬重启
Get-Process python | Stop-Process -Force
os-node run
```

### 超时后进程未停止

**原因**：当前实现不向旧进程发送显式关闭信号。
- 旧进程继续运行直到下一个心跳 tick
- 新进程并行启动（可能导致端口冲突）

**缓解**：
```powershell
# 选项 A：手动停止旧进程
Get-Process python | Where-Object {$_.Id -eq <old_pid>} | Stop-Process -Force

# 选项 B：使用更长的超时以允许自然完成
os-node restart --graceful --timeout 30

# 选项 C：增加原始运行命令中的 --interval
os-node run --interval 10  # 每 10s 一次心跳（默认：5s）
```

---

## 最佳实践

### ✅ 推荐做法

1. **在生产中使用优雅重启**
   ```powershell
   os-node restart --graceful --timeout 30
   ```

2. **重启后监控新进程**
   ```powershell
   Sleep 5; os-node status
   ```

3. **记录所有重启操作**（用于审计追踪）
   ```powershell
   "[$(Get-Date)] 重启已启动" | Out-File -Append restart.log
   os-node restart --graceful --timeout 10
   ```

4. **批处理操作使用更长的超时**
   ```powershell
   os-node restart --graceful --timeout 60  # 1 分钟用于大型批处理
   ```

### ❌ 不推荐做法

1. ❌ **在传输大量数据时使用重启**
   - 改为：增加超时或等待传输完成

2. ❌ **同时重启多个进程**（端口冲突）
   - 改为：逐个重启，或使用不同端口

3. ❌ **忽略新进程窗口**（Windows）
   - 改为：保持终端 B 可见以监控重启进度

4. ❌ **依赖重启进行错误恢复**
   - 改为：使用 `deps --cmd repair` 或 `native-build` 处理依赖问题

---

## 性能影响

### 重启开销

| 阶段 | 持续时间 | 说明 |
|------|---------|------|
| 新进程生成 | ~50–200 ms | 取决于系统负载 |
| Config 加载 | ~10–50 ms | 缓存的 config.json 解析 |
| 插件初始化 | ~100–500 ms | 接收器启动等 |
| **总计** | **~0.2–0.8 sec** | 典型情况 |

### 比较：重启 vs. 手动停止+启动

| 方法 | 时间 | 用户步骤 |
|------|------|---------|
| `os-node restart --graceful` | ~0.2–0.8s | 1 条命令 |
| 手动：Ctrl+C 然后 `os-node run` | ~1.0–2.0s | 2 步 + 焦点切换 |

---

## 与其他命令的集成

### 重启 + 状态检查

```powershell
os-node restart --graceful && Start-Sleep 5 && os-node status
```

### 重启 + 配置更新

```powershell
os-node config-set --key engine_settings.precision --value 6 --type int
os-node restart --graceful --timeout 5
```

### 重启 + 插件测试

```powershell
os-node restart --graceful
os-node plugin-test --suite component
```

### 循环式重启（生产监控）

```powershell
# 每小时重启一次并记录结果
for ($i = 0; $i -lt 24; $i++) {
    "[$([DateTime]::Now)] 第 $($i+1) 小时：运行插件测试..." > test_$i.log
    os-node plugin-test --suite stress --total 100 2>&1 | Tee-Object -Append test_$i.log
    
    "[$([DateTime]::Now)] 优雅重启..." >> test_$i.log
    os-node restart --graceful --timeout 30
    
    Start-Sleep -Seconds 3600
}
```

---

## FAQ

**Q：我可以不带 graceful 标志重启吗？**
A：可以。`--graceful` 默认启用。要禁用：`--no-graceful`（如果已实现）。

**Q：重启会丢失我的数据吗？**
A：不会。Config.json 和 data/ 目录会保留。仅内存中的协议状态会重置（通常对无状态协议来说没问题）。

**Q：接收数据时可以重启吗？**
A：可以，但使用更长的超时（例如 `--timeout 30`）以允许处理当前数据包。

**Q：重启在 Linux/macOS 上工作吗？**
A：可以。Windows 使用 `CREATE_NEW_CONSOLE` 标志；类 Unix 系统使用 `os.setsid()` 进行进程分离。

**Q：我如何编写每小时重启脚本？**
A：参见上面的"循环式重启（生产监控）"部分。

**Q：新进程启动失败怎么办？**
A：错误记录到 `os_log` 并打印到终端 B。检查 Config.json 有效性和依赖状态。

---

## 另请参阅

- [README.md](../../README.md) – CLI 快速参考
- [src/opensynaptic/CLI/README.md](../../src/opensynaptic/CLI/README.md) – 详细 CLI 示例
- [ARCHITECTURE.md](../ARCHITECTURE.md) – 系统架构
- [CONFIG_SCHEMA.md](../CONFIG_SCHEMA.md) – 配置参考
