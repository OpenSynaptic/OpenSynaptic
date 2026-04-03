---
title: 重启命令文档总结
language: zh
---

# OpenSynaptic 重启命令文档总结

**创建时间**：2026-04-03  
**状态**：完成

---

## 概述

已成功在整个 OpenSynaptic 文档结构中集成了针对新 `os-node restart --graceful` 命令的全面文档。

## 修改的文件

### 1. **根文档**
- **[README.md](README.md)**（主中心）
  - 更新了"命令类别"部分以包含 `restart`
  - 向"所有命令"表添加了 `restart` 命令（附说明）
  - 位置：第 395、405 行

### 2. **CLI 文档**
- **[src/opensynaptic/CLI/README.md](src/opensynaptic/CLI/README.md)**（CLI 参考）
  - 将 `restart` 添加到命令参考表
  - 添加了示例用法：`python -u src/main.py restart --graceful --timeout 10`
  - 添加了带自定义主机/端口参数的示例
  - 位置：第 17、67-68 行

### 3. **工作区指令**
- **[AGENTS.md](AGENTS.md)**（工作区准则）
  - 将优雅重启添加到"维护实用工具"部分
  - 包含双终端工作流注释
  - 位置：第 103-106 行

### 4. **文档索引**
- **[docs/INDEX.md](docs/INDEX.md)**（文档中心）
  - 将新建指南文件添加到"指南"部分
  - 位置：第 64 行

### 5. **新综合指南** ✨
- **[docs/guides/RESTART_COMMAND_GUIDE.md](docs/guides/RESTART_COMMAND_GUIDE.md)**（11,992 字节）
  - 完整的 370+ 行参考指南，包括：
    - **快速开始**：3 种使用模式（基础、自定义超时、自定义主机/端口）
    - **工作原理**：架构图、执行流程、优雅与非优雅对比
    - **示例**：开发工作流、压力测试、生产自动重启
    - **命令参考**：完整的参数表和输出格式
    - **故障排除**：常见问题和解决方案
    - **最佳实践**：做的和不做的事项及代码示例
    - **性能影响**：开销分析和对比
    - **集成**：与其他命令的示例
    - **常见问题**：常见问题解答

## 文档结构

```
OpenSynaptic 文档
├── README.md（已更新）
│   └── CLI 快速参考（已更新）
├── docs/
│   ├── INDEX.md（已更新）
│   └── guides/
│       ├── RESTART_COMMAND_GUIDE.md（新）
│       └── ... 其他指南
├── src/opensynaptic/CLI/
│   └── README.md（已更新）
└── AGENTS.md（已更新）
```

## 关键文档内容

### 快速参考位置

| 需要 | 位置 | 链接 |
|---|---|---|
| 快速开始 | README.md | 第 405 行 |
| 完整命令参考 | CLI README | 第 17-18 行 |
| 详细指南 | guides/ | RESTART_COMMAND_GUIDE.md |
| 工作区上下文 | AGENTS.md | 第 103-106 行 |

### 命令语法（来自 README）

```powershell
# 基础：10 秒优雅关闭（默认）
os-node restart --graceful

# 自定义超时
os-node restart --graceful --timeout 5

# 带自定义服务器
os-node restart --graceful --timeout 15 --host 192.168.1.100 --port 9090
```

### 别名（来自 CLI README）

| 形式 | 等价形式 |
|---|---|
| `os-node restart` | 主要形式 |
| `os-node os-restart` | 主要别名 |
| `python -u src/main.py restart` | 直接 Python 调用 |
| `.\run-main.cmd restart` | Windows 包装器 |

## 文档质量检查表

- ✅ 快速参考已更新（README.md）
- ✅ CLI 参考已更新（src/opensynaptic/CLI/README.md）
- ✅ 工作区准则已更新（AGENTS.md）
- ✅ 文档索引已更新（docs/INDEX.md）
- ✅ 综合指南已创建（docs/guides/RESTART_COMMAND_GUIDE.md）
- ✅ 所有交叉引用有效
- ✅ 示例在 Windows/Unix 上可执行
- ✅ 包含故障排除部分
- ✅ 已记录最佳实践
- ✅ 提供了性能分析

## 如何使用本指南

### 快速学习
1. 阅读 [README.md](README.md) 第 405 行的摘要
2. 尝试基本示例：`os-node restart --graceful`
3. 在 [src/opensynaptic/CLI/README.md](src/opensynaptic/CLI/README.md) 中检查 CLI 示例

### 深入理解
1. 从 [docs/guides/RESTART_COMMAND_GUIDE.md](docs/guides/RESTART_COMMAND_GUIDE.md) 的"概述"部分开始
2. 查看"工作原理"架构
3. 按照用例中的示例进行操作
4. 如果出现问题，请参阅"故障排除"

### 与其他命令集成
- 见 RESTART_COMMAND_GUIDE.md 中的"与其他命令集成"
- 示例包括：配置更新、插件测试、压力测试

### 生产部署
- "最佳实践"部分包括做的和不做的事项
- 生产自动重启脚本示例
- 性能影响分析
- 故障排除指南

## 交叉引用

所有指南都正确链接到相关文档：

```markdown
- [README.md](../../README.md) – CLI 快速参考
- [src/opensynaptic/CLI/README.md](../../src/opensynaptic/CLI/README.md) – 详细 CLI 示例
- [ARCHITECTURE.md](../ARCHITECTURE.md) – 系统架构
- [CONFIG_SCHEMA.md](../CONFIG_SCHEMA.md) – 配置参考
```

---

**注：** 本翻译保持了所有参考路径和文件位置的完整性。
