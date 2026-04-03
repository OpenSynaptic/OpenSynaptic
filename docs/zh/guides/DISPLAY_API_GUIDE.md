---
layout: default
title: 显示 API 指南 - 自发现可视化系统
language: zh
---

# 显示 API：自发现可视化系统

## 概述

显示 API 提供了基于插件的自发现可视化架构。与在 web_user 和 tui 中硬编码显示逻辑不同，插件现在可以注册自定义"显示提供程序"，定义如何提取和格式化数据以进行可视化。

**主要好处**：
- **无硬编码** - 插件定义自己的显示部分
- **自动发现** - web_user 和 tui 自动发现所有已注册的提供程序
- **多种格式** - 每个提供程序都可以支持 JSON、HTML、文本、表格或树形输出
- **可扩展** - 新插件可注册新显示部分，无需修改核心代码
- **统一 API** - Web 和终端 UI 的单一接口

---

## 架构

### 核心组件

1. **DisplayProvider**（抽象基类）
   - 插件通过子类化来提供自定义显示部分
   - 实现 `extract_data()` 以获取相关信息
   - 提供格式方法：`format_json()`、`format_html()`、`format_text()`、`format_table()`、`format_tree()`

2. **DisplayRegistry**（全局单例）
   - 维护所有已注册显示提供程序的注册表
   - 支持按类别和优先级过滤
   - 线程安全操作

3. **web_user 集成**
   - 新 HTTP 端点：`/api/display/providers`、`/api/display/render/{section}`、`/api/display/all`
   - 自动调用显示提供程序以构建仪表板
   - 通过查询参数支持多种输出格式

4. **tui 集成**
   - 动态节列表，包含内置和提供程序节
   - 新命令：`[m]` 用于元数据，`[s]` 用于搜索
   - 无缝将提供程序输出集成到 BIOS 控制台

---

## 创建显示提供程序插件

### 最小示例

```python
from opensynaptic.services.display_api import DisplayProvider, register_display_provider

class MyCustomDisplayProvider(DisplayProvider):
    """自定义显示提供程序。"""
    
    def __init__(self):
        super().__init__(
            plugin_name='my_plugin',
            section_id='custom_metrics',
            display_name='自定义指标仪表板'
        )
        self.category = 'custom'
        self.priority = 75
        self.refresh_interval_s = 5.0
    
    def extract_data(self, node=None, **kwargs):
        """从节点提取数据。"""
        return {
            'total_items': 42,
            'active': True,
            'timestamp': int(__import__('time').time()),
        }

def auto_load(config=None):
    """插件自动加载函数。"""
    register_display_provider(MyCustomDisplayProvider())
    return True
```

### 完整示例，包含自定义格式化

```python
from opensynaptic.services.display_api import DisplayProvider, register_display_provider

class MetricsDisplayProvider(DisplayProvider):
    
    def __init__(self):
        super().__init__(
            plugin_name='metrics_plugin',
            section_id='system_metrics',
            display_name='系统指标'
        )
        self.category = 'metrics'
        self.priority = 80
    
    def extract_data(self, node=None, **kwargs):
        # 自定义数据提取逻辑
        return {
            'cpu_usage': 45.2,
            'memory_usage': 78.5,
            'network_io': 1024,
            'disk_io': 512,
        }
    
    def format_html(self, data):
        """自定义 HTML 渲染。"""
        return f"""
        <div style="padding: 15px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px; color: white;">
            <h2>系统指标</h2>
            <table style="width: 100%; color: white;">
                <tr><td>CPU</td><td>{data['cpu_usage']:.1f}%</td></tr>
                <tr><td>内存</td><td>{data['memory_usage']:.1f}%</td></tr>
                <tr><td>网络 I/O</td><td>{data['network_io']} 字节/秒</td></tr>
                <tr><td>磁盘 I/O</td><td>{data['disk_io']} 字节/秒</td></tr>
            </table>
        </div>
        """
    
    def format_text(self, data):
        """为终端提供自定义文本渲染。"""
        lines = [
            "╔════════════════════════════════╗",
            "║     系统指标                    ║",
            "╠════════════════════════════════╣",
            f"║ CPU 使用率：   {data['cpu_usage']:>6.1f}%        ║",
            f"║ 内存使用率：   {data['memory_usage']:>6.1f}%        ║",
            f"║ 网络 I/O：     {data['network_io']:>6} 字节/秒  ║",
            f"║ 磁盘 I/O：     {data['disk_io']:>6} 字节/秒  ║",
            "╚════════════════════════════════╝"
        ]
        return "\n".join(lines)

def auto_load(config=None):
    register_display_provider(MetricsDisplayProvider())
    return True
```

---

## API 参考

### DisplayProvider 类

#### 构造函数
```python
DisplayProvider(plugin_name: str, section_id: str, display_name: str = None)
```

**属性**：
- `plugin_name` - 插件名称（例如 'id_allocator'、'test_plugin'）
- `section_id` - 插件内的唯一部分标识符（例如 'metrics'、'status'）
- `display_name` - 人类可读的显示名称（默认为 section_id）
- `category` - 分类标签（默认：'plugin'）
- `priority` - 显示优先级 0-100，数值越高越优先显示（默认：50）
- `refresh_interval_s` - 建议的刷新时间间隔（默认：2.0）

#### 抽象方法
```python
extract_data(self, node=None, **kwargs) -> Dict[str, Any]
```

必须由子类实现。返回包含提取数据的字典。

#### 格式化方法

所有格式化方法都接收 `extract_data()` 返回的字典，并返回格式化的输出。

```python
def format_json(self, data: Dict) -> Dict:
    """返回 JSON 可序列化字典。默认：原样返回数据。"""
    return data

def format_html(self, data: Dict) -> str:
    """返回 HTML 字符串。默认：生成基本表格。"""
    return "<table>...</table>"

def format_text(self, data: Dict) -> str:
    """返回纯文本。默认：美化打印 JSON。"""
    return "key: value\n..."

def format_table(self, data: Dict) -> List[Dict]:
    """返回表格数据（行）。默认：将数据包装在列表中。"""
    return [data]

def format_tree(self, data: Dict) -> Dict:
    """返回分层结构。默认：原样返回数据。"""
    return data

def supports_format(self, fmt: DisplayFormat) -> bool:
    """检查是否支持格式。默认：支持所有。"""
    return True
```

### 注册表函数

```python
from opensynaptic.services.display_api import (
    get_display_registry,
    register_display_provider,
    render_section,
    collect_all_sections,
    DisplayFormat,
)

# 注册提供程序
register_display_provider(MyProvider())

# 获取全局注册表
registry = get_display_registry()

# 获取提供程序元数据
metadata = registry.get_metadata()
metadata = registry.get_metadata(plugin_name='my_plugin')

# 列出提供程序
providers = registry.list_all()  # 按优先级排序
providers = registry.list_by_category('metrics')

# 列出类别
categories = registry.list_categories()

# 渲染特定部分
output = render_section(
    plugin_name='my_plugin',
    section_id='metrics',
    fmt=DisplayFormat.JSON,
    node=node_instance
)

# 收集所有部分
all_data = collect_all_sections(fmt=DisplayFormat.JSON, node=node_instance)
```

---

## web_user HTTP API

### 新端点

#### GET /api/display/providers
返回所有已注册显示提供程序的元数据。

**响应**：
```json
{
  "ok": true,
  "metadata": {
    "total_providers": 3,
    "categories": ["core", "metrics", "transport"],
    "providers": [
      {
        "plugin_name": "id_allocator",
        "section_id": "lease_metrics",
        "display_name": "ID 租赁指标",
        "category": "metrics",
        "priority": 80,
        "refresh_interval_s": 5.0
      }
    ]
  }
}
```

#### GET /api/display/render/{plugin_name}:{section_id}?format=json
渲染特定显示部分。

**查询参数**：
- `format` - 输出格式：`json`、`html`、`text`、`table`、`tree`（默认：`json`）

**响应**：
```json
{
  "ok": true,
  "section": "my_plugin:metrics",
  "format": "json",
  "data": { "metric1": 42, "metric2": 100 }
}
```

#### GET /api/display/all?format=json
收集所有已注册的显示部分。

**查询参数**：
- `format` - 输出格式（默认：`json`）

**响应**：
```json
{
  "ok": true,
  "format": "json",
  "sections": {
    "core": {
      "node_stats": { "device_id": "sensor-001", "assigned_id": 12345 },
      "pipeline_metrics": { "cache_entries": 256 }
    },
    "metrics": {
      "system_metrics": { "cpu": 45.2, "memory": 78.5 }
    }
  },
  "timestamp": 1711864234
}
```

---

## tui 集成

### 动态部分发现

tui 现在自动将显示提供程序部分包含在其部分列表中：

```
| OpenSynaptic BIOS 控制台（包含显示 API 提供程序）
| 内置部分：
|   * 1. 配置
|   2. 传输
|   3. 管道
|   4. 插件
|   5. 数据库
|   6. 身份
| 显示 API 提供程序：
|   7. id_allocator:lease_metrics
|   8. test_plugin:performance
|   9. example_display:node_stats
```

### 新命令

- `[1-N]` - 按编号切换到部分（包括提供程序）
- `[m]` - 显示所有提供程序的元数据
- `[s]` - 按部分名称搜索部分
- `[a]` - 显示所有部分（内置 + 提供程序）
- `[r]` - 刷新当前部分
- `[j]` - 将当前部分打印为 JSON
- `[auto N]` - 自动刷新 N 个周期
- `[i SEC]` - 设置刷新间隔
- `[p]` - 列表可用插件
- `[h]` - 显示帮助
- `[q]` - 退出

### 示例会话

```
bios> m
{
  "builtin": ["config", "transport", "pipeline", "plugins", "db", "identity"],
  "providers": {
    "total_providers": 3,
    "categories": ["metrics", "custom"],
    "providers": [...]
  }
}

bios> s metrics
{
  "matching": [
    "id_allocator:lease_metrics",
    "test_plugin:performance"
  ]
}

bios> 7
[显示部分：id_allocator:lease_metrics]
```

---

## 示例：带显示提供程序的完整插件

文件：`plugins/my_analytics_plugin.py`

```python
"""
具有显示提供程序的分析插件。

通过显示 API 提供自定义指标可视化。
"""

from typing import Dict, Any
from opensynaptic.services.display_api import DisplayProvider, register_display_provider
import time


class AnalyticsMetricsDisplayProvider(DisplayProvider):
    """显示分析指标。"""
    
    def __init__(self):
        super().__init__(
            plugin_name='my_analytics',
            section_id='metrics',
            display_name='分析指标'
        )
        self.category = 'metrics'
        self.priority = 85
        self.refresh_interval_s = 5.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        # 示例：从节点或任何其他来源提取
        return {
            'requests_total': 15234,
            'requests_per_second': 42.5,
            'errors': 12,
            'avg_latency_ms': 145.3,
            'p99_latency_ms': 523.8,
            'timestamp': int(time.time()),
        }
    
    def format_html(self, data: Dict[str, Any]) -> str:
        return f"""
        <div style="padding: 15px; background: #f0f4f8; border-radius: 8px;">
            <h3>分析</h3>
            <ul>
                <li><strong>总请求：</strong> {data['requests_total']}</li>
                <li><strong>RPS：</strong> {data['requests_per_second']}</li>
                <li><strong>错误：</strong> {data['errors']}</li>
                <li><strong>平均延迟：</strong> {data['avg_latency_ms']:.1f}ms</li>
                <li><strong>P99 延迟：</strong> {data['p99_latency_ms']:.1f}ms</li>
            </ul>
        </div>
        """


class AnalyticsStatusDisplayProvider(DisplayProvider):
    """显示分析系统状态。"""
    
    def __init__(self):
        super().__init__(
            plugin_name='my_analytics',
            section_id='status',
            display_name='分析状态'
        )
        self.category = 'custom'
        self.priority = 70
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        return {
            'system_status': '健康',
            'backend_connected': True,
            'db_connected': True,
            'cache_size_mb': 512,
        }


def auto_load(config=None):
    """插件加载时注册显示提供程序。"""
    register_display_provider(AnalyticsMetricsDisplayProvider())
    register_display_provider(AnalyticsStatusDisplayProvider())
    
    from opensynaptic.utils import os_log
    os_log.info(
        'MY_ANALYTICS',
        'DISPLAY_PROVIDERS_REGISTERED',
        '分析显示提供程序已注册',
        {'providers': ['metrics', 'status']}
    )
    
    return True
```

---

## 最佳实践

1. **保持 extract_data() 快速** - 它在刷新期间被频繁调用
2. **使用适当的类别** - 'metrics'、'core'、'transport'、'custom' 等
3. **设置合理的优先级** - 较高优先级的部分优先显示
4. **选择性实现格式方法** - 仅覆盖需要的内容
5. **返回 JSON 可序列化数据** - JSON 格式是默认值
6. **优雅处理缺失 node** - `node` 在某些上下文中可能为 None
7. **使用一致的显示名称** - 使其用户友好
8. **同时使用 web_user 和 tui 进行测试** - 确保输出适用于两个 UI

---

## 测试显示提供程序

### 命令行

```bash
# 列出所有提供程序
python -u src/main.py example_display list

# 渲染特定部分
python -u src/main.py example_display render example_display node_stats --format json

# 收集所有部分
python -u src/main.py example_display collect --format json

# 渲染为 HTML
python -u src/main.py example_display render my_plugin metrics --format html
```

### web_user

```bash
# 查看提供程序元数据
curl http://localhost:8765/api/display/providers

# 渲染特定部分
curl http://localhost:8765/api/display/render/my_plugin:metrics?format=json

# 获取所有部分作为 HTML
curl http://localhost:8765/api/display/all?format=html
```

### tui

```bash
# 进入 TUI 并按 'm' 查看提供程序元数据
python -u src/main.py tui interactive --section identity

# 在 BIOS 内，使用 's' 搜索部分
# 使用 '7'、'8'、'9' 等查看提供程序部分
```

---

## 迁移指南：从硬编码到显示 API

### 之前（在 tui 中硬编码）
```python
def _section_custom(self):
    return {
        'metric1': get_metric1(),
        'metric2': get_metric2(),
    }

_SECTION_METHODS = {
    ...
    'custom': '_section_custom',
}
```

### 之后（显示提供程序）
```python
# 在你的插件中
class MyDisplayProvider(DisplayProvider):
    def __init__(self):
        super().__init__('my_plugin', 'metrics')
    
    def extract_data(self, node=None, **kwargs):
        return {
            'metric1': get_metric1(),
            'metric2': get_metric2(),
        }

def auto_load(config=None):
    register_display_provider(MyDisplayProvider())
    return True
```

现在 tui 和 web_user 自动发现和渲染它，无需任何硬编码！

---

## 故障排除

**提供程序未出现在 web_user 或 tui 中**：
- 检查插件是否被加载（在 `plugin-test` 或 tui `[p]` 命令中可见）
- 验证在 `auto_load()` 中调用了 `register_display_provider()`
- 使用 curl 检查注册表：`GET /api/display/providers`

**渲染部分时出错**：
- 检查 `extract_data()` 是否不抛出异常
- 确保返回的数据是 JSON 可序列化的
- 检查日志：搜索 `DISPLAY_RENDER_ERROR`

**HTML 格式渲染不正确**：
- 在 `curl` 中测试：`GET /api/display/render/plugin:section?format=html`
- 验证 HTML 是否正确转义
- 检查浏览器控制台中的渲染错误

**性能问题**：
- 减少提供程序中的 refresh_interval_s
- 优化 extract_data() 以更快
- 考虑在提供程序内缓存数据

---

## 另请参阅

- `src/opensynaptic/services/display_api.py` - 核心显示 API 实现
- `src/opensynaptic/services/example_display_plugin.py` - 参考示例
- `src/opensynaptic/services/tui/main.py` - tui 集成
- `src/opensynaptic/services/web_user/main.py` - web_user 集成
- `Config.json` - web_user 中的 `expose_sections` 配置
