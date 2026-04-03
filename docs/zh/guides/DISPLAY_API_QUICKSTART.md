---
layout: default
title: 显示 API 快速开始指南
language: zh
---

# 显示 API 快速开始指南

## 有什么改变？

web_user 和 tui 不再拥有硬编码的显示部分。取而代之的是，它们自动发现由插件注册的"显示提供程序"。这使得任何插件都可以轻松贡献自定义可视化，而无需修改核心代码。

## 5 分钟快速开始

### 1. 创建显示提供程序

在你的插件文件中添加显示提供程序类：

```python
from opensynaptic.services.display_api import DisplayProvider, register_display_provider

class MyMetricsDisplay(DisplayProvider):
    def __init__(self):
        super().__init__(
            plugin_name='my_plugin',
            section_id='metrics',
            display_name='我的指标'
        )
    
    def extract_data(self, node=None, **kwargs):
        return {
            'value1': 42,
            'value2': 100,
            'status': '健康'
        }

def auto_load(config=None):
    register_display_provider(MyMetricsDisplay())
    return True
```

### 2. 通过 web_user 访问

```bash
# 获取所有提供程序
curl http://localhost:8765/api/display/providers

# 渲染你的部分
curl http://localhost:8765/api/display/render/my_plugin:metrics

# 从所有提供程序获取所有部分
curl http://localhost:8765/api/display/all
```

### 3. 通过 tui 访问

```bash
# 在 BIOS 控制台中
bios> m              # 查看提供程序元数据
bios> s metrics      # 搜索部分
bios> 7              # 切换到部分 7（你的新部分）
bios> j              # 查看为 JSON
```

## 关键文件

| 文件 | 用途 |
|------|------|
| `src/opensynaptic/services/display_api.py` | 核心显示 API 实现 |
| `src/opensynaptic/services/example_display_plugin.py` | 参考示例 |
| `src/opensynaptic/services/tui/main.py` | tui 集成（已更新）|
| `src/opensynaptic/services/web_user/main.py` | web_user 集成（已更新）|
| `src/opensynaptic/services/web_user/handlers.py` | 新 HTTP 端点（已更新）|
| `DISPLAY_API_GUIDE.md` | 完整文档 |

## 快速参考：DisplayProvider API

### 创建提供程序
```python
class MyProvider(DisplayProvider):
    def __init__(self):
        super().__init__(
            plugin_name='my_plugin',
            section_id='my_section',
            display_name='显示名称'
        )
        self.category = 'metrics'           # 'metrics'、'core'、'custom' 等
        self.priority = 75                  # 0-100，数值越高越优先显示
        self.refresh_interval_s = 5.0       # 建议刷新率
    
    def extract_data(self, node=None, **kwargs):
        # 返回包含你的数据的字典
        return {'key': 'value'}
    
    # 可选：自定义格式化
    def format_html(self, data):
        return "<div>自定义 html</div>"
```

### 注册提供程序
```python
from opensynaptic.services.display_api import register_display_provider

def auto_load(config=None):
    register_display_provider(MyProvider())
    return True
```

### 输出格式

你的提供程序可自动支持这些格式：
- **JSON** - 字典，默认 `format_json()`
- **HTML** - HTML 字符串，默认生成表格
- **TEXT** - 纯文本，默认美化打印 JSON
- **TABLE** - 字典列表/2D 数组，默认在列表中包装
- **TREE** - 分层字典，默认原样返回

## Web API 端点

### GET /api/display/providers
获取所有已注册提供程序的元数据
```json
{"ok": true, "metadata": {...}}
```

### GET /api/display/render/{plugin}:{section}?format=json
渲染特定部分
```json
{"ok": true, "section": "plugin:section", "format": "json", "data": {...}}
```

### GET /api/display/all?format=json
从所有提供程序获取所有部分
```json
{"ok": true, "format": "json", "sections": {...}, "timestamp": ...}
```

## TUI 命令

| 命令 | 描述 |
|------|------|
| `1-N` | 切换到编号部分（包括提供程序）|
| `a` | 显示所有部分 |
| `r` | 刷新当前部分 |
| `j` | 打印为 JSON |
| `m` | 显示提供程序元数据 |
| `s` | 搜索部分 |
| `p` | 列表插件 |
| `auto N` | 自动刷新 N 个周期 |
| `i SEC` | 设置刷新间隔 |
| `h` | 显示帮助 |
| `q` | 退出 |

## 示例：ID 分配器插件

如果 id_allocator 插件注册了显示提供程序：

```python
# 在 id_allocator.py 中
class IDLeaseMetricsDisplay(DisplayProvider):
    def __init__(self):
        super().__init__('id_allocator', 'lease_metrics', 'ID 租赁指标')
        self.category = 'metrics'
        self.priority = 80
    
    def extract_data(self, node=None, **kwargs):
        # 访问节点以获取数据
        allocator = getattr(node, 'id_allocator', None)
        return {
            'total_allocated': allocator.total_allocated,
            'active_ids': len(allocator.active_ids),
            'effective_lease_seconds': allocator.effective_lease_seconds,
        }
```

然后：
1. **web_user**：`GET /api/display/render/id_allocator:lease_metrics`
2. **tui**：输入部分编号以查看指标
3. **无需硬编码！**

## 测试你的提供程序

### 选项 1：使用 CLI
```bash
python -u src/main.py example_display list
python -u src/main.py example_display render my_plugin my_section --format json
```

### 选项 2：使用 web_user
```bash
# 启动 web_user
python -u src/main.py web_user start &

# 测试端点
curl http://localhost:8765/api/display/providers
curl http://localhost:8765/api/display/render/my_plugin:my_section
```

### 选项 3：使用 tui
```bash
python -u src/main.py tui interactive
# 在 BIOS 中，按 'm' 查看所有提供程序
```

## 常见模式

### 指标显示
```python
class MetricsProvider(DisplayProvider):
    def __init__(self):
        super().__init__('metrics_plugin', 'perf', '性能')
        self.category = 'metrics'
        self.priority = 85
    
    def extract_data(self, node=None, **kwargs):
        return {'cpu': 45.2, 'memory': 78.5, 'disk': 60.0}
    
    def format_html(self, data):
        bars = ''.join(f"<div>{k}: {'▓'*int(v/10)}{'░'*int((100-v)/10)}</div>"
                       for k, v in data.items())
        return f"<div style='font-family:monospace'>{bars}</div>"
```

### 状态显示
```python
class StatusProvider(DisplayProvider):
    def __init__(self):
        super().__init__('status_plugin', 'health', '健康状态')
        self.category = 'core'
        self.priority = 90
    
    def extract_data(self, node=None, **kwargs):
        return {
            'transport': '健康' if node.is_transport_ready else '故障',
            'database': '已连接' if node.db_ready else '错误',
            'uptime_s': node.uptime_seconds,
        }
```

### 配置显示
```python
class ConfigProvider(DisplayProvider):
    def __init__(self):
        super().__init__('config_plugin', 'active', '活跃配置')
        self.category = 'core'
    
    def extract_data(self, node=None, **kwargs):
        cfg = node.config if node else {}
        return {
            'core_backend': cfg.get('engine_settings', {}).get('core_backend'),
            'precision': cfg.get('engine_settings', {}).get('precision'),
            'compression_enabled': cfg.get('engine_settings', {}).get('active_compression'),
        }
```

## 优势

✅ **无硬编码** - 插件定义自己的显示
✅ **自动发现** - web_user 和 tui 发现所有提供程序
✅ **灵活** - 支持 JSON、HTML、文本、表格、树形格式
✅ **可扩展** - 添加新提供程序而无需触及核心代码
✅ **统一** - Web 和终端 UI 的单一 API
✅ **易于测试** - 通过 CLI、Web 或 tui 测试

## 另请参阅

- **完整指南**：`DISPLAY_API_GUIDE.md`
- **参考实现**：`src/opensynaptic/services/example_display_plugin.py`
- **核心模块**：`src/opensynaptic/services/display_api.py`
