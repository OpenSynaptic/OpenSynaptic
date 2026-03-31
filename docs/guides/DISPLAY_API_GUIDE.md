Display API: Self-Discoverable Visualization System
===================================================

## Overview

The Display API provides a plugin-based architecture for self-discoverable visualization. Instead of hardcoding display logic in web_user and tui, plugins can now register custom "display providers" that define how to extract and format data for visualization.

**Key Benefits:**
- **No hardcoding** - plugins define their own display sections
- **Auto-discovery** - web_user and tui automatically discover all registered providers
- **Multiple formats** - each provider can support JSON, HTML, text, table, or tree output
- **Extensible** - new plugins can register new display sections without modifying core code
- **Unified API** - single interface for both web and terminal UIs

---

## Architecture

### Core Components

1. **DisplayProvider** (abstract base class)
   - Plugins subclass this to provide custom display sections
   - Implements `extract_data()` to fetch relevant information
   - Provides format methods: `format_json()`, `format_html()`, `format_text()`, `format_table()`, `format_tree()`

2. **DisplayRegistry** (global singleton)
   - Maintains a registry of all registered display providers
   - Supports filtering by category and priority
   - Thread-safe operations

3. **web_user Integration**
   - New HTTP endpoints: `/api/display/providers`, `/api/display/render/{section}`, `/api/display/all`
   - Automatically calls display providers to build dashboards
   - Supports multiple output formats via query parameters

4. **tui Integration**
   - Dynamic section list that includes both built-in and provider sections
   - New commands: `[m]` for metadata, `[s]` for search
   - Seamlessly integrates provider output into BIOS console

---

## Creating a Display Provider Plugin

### Minimal Example

```python
from opensynaptic.services.display_api import DisplayProvider, register_display_provider

class MyCustomDisplayProvider(DisplayProvider):
    """Custom display provider for my plugin."""
    
    def __init__(self):
        super().__init__(
            plugin_name='my_plugin',
            section_id='custom_metrics',
            display_name='Custom Metrics Dashboard'
        )
        self.category = 'custom'
        self.priority = 75
        self.refresh_interval_s = 5.0
    
    def extract_data(self, node=None, **kwargs):
        """Extract data from node."""
        return {
            'total_items': 42,
            'active': True,
            'timestamp': int(__import__('time').time()),
        }

def auto_load(config=None):
    """Plugin auto-load function."""
    register_display_provider(MyCustomDisplayProvider())
    return True
```

### Full Example with Custom Formatting

```python
from opensynaptic.services.display_api import DisplayProvider, register_display_provider

class MetricsDisplayProvider(DisplayProvider):
    
    def __init__(self):
        super().__init__(
            plugin_name='metrics_plugin',
            section_id='system_metrics',
            display_name='System Metrics'
        )
        self.category = 'metrics'
        self.priority = 80
    
    def extract_data(self, node=None, **kwargs):
        # Custom data extraction logic
        return {
            'cpu_usage': 45.2,
            'memory_usage': 78.5,
            'network_io': 1024,
            'disk_io': 512,
        }
    
    def format_html(self, data):
        """Custom HTML rendering."""
        return f"""
        <div style="padding: 15px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px; color: white;">
            <h2>System Metrics</h2>
            <table style="width: 100%; color: white;">
                <tr><td>CPU</td><td>{data['cpu_usage']:.1f}%</td></tr>
                <tr><td>Memory</td><td>{data['memory_usage']:.1f}%</td></tr>
                <tr><td>Network I/O</td><td>{data['network_io']} bytes/s</td></tr>
                <tr><td>Disk I/O</td><td>{data['disk_io']} bytes/s</td></tr>
            </table>
        </div>
        """
    
    def format_text(self, data):
        """Custom text rendering for terminal."""
        lines = [
            "╔════════════════════════════════╗",
            "║     System Metrics              ║",
            "╠════════════════════════════════╣",
            f"║ CPU Usage:     {data['cpu_usage']:>6.1f}%        ║",
            f"║ Memory Usage:  {data['memory_usage']:>6.1f}%        ║",
            f"║ Network I/O:   {data['network_io']:>6} bytes/s  ║",
            f"║ Disk I/O:      {data['disk_io']:>6} bytes/s  ║",
            "╚════════════════════════════════╝"
        ]
        return "\n".join(lines)

def auto_load(config=None):
    register_display_provider(MetricsDisplayProvider())
    return True
```

---

## API Reference

### DisplayProvider Class

#### Constructor
```python
DisplayProvider(plugin_name: str, section_id: str, display_name: str = None)
```

**Attributes:**
- `plugin_name` - Name of the plugin (e.g., 'id_allocator', 'test_plugin')
- `section_id` - Unique section identifier within the plugin (e.g., 'metrics', 'status')
- `display_name` - Human-readable display name (defaults to section_id)
- `category` - Category for grouping (default: 'plugin')
- `priority` - Display priority 0-100, higher = shown first (default: 50)
- `refresh_interval_s` - Suggested refresh interval (default: 2.0)

#### Abstract Method
```python
extract_data(self, node=None, **kwargs) -> Dict[str, Any]
```

Must be implemented by subclasses. Returns a dict with extracted data.

#### Format Methods

All format methods receive the dict returned by `extract_data()` and return formatted output.

```python
def format_json(self, data: Dict) -> Dict:
    """Return JSON-serializable dict. Default: returns data as-is."""
    return data

def format_html(self, data: Dict) -> str:
    """Return HTML string. Default: generates basic table."""
    return "<table>...</table>"

def format_text(self, data: Dict) -> str:
    """Return plain text. Default: pretty-prints JSON."""
    return "key: value\n..."

def format_table(self, data: Dict) -> List[Dict]:
    """Return tabular data (rows). Default: wraps data in list."""
    return [data]

def format_tree(self, data: Dict) -> Dict:
    """Return hierarchical structure. Default: returns data as-is."""
    return data

def supports_format(self, fmt: DisplayFormat) -> bool:
    """Check if format is supported. Default: supports all."""
    return True
```

### Registry Functions

```python
from opensynaptic.services.display_api import (
    get_display_registry,
    register_display_provider,
    render_section,
    collect_all_sections,
    DisplayFormat,
)

# Register a provider
register_display_provider(MyProvider())

# Get the global registry
registry = get_display_registry()

# Get provider metadata
metadata = registry.get_metadata()
metadata = registry.get_metadata(plugin_name='my_plugin')

# List providers
providers = registry.list_all()  # sorted by priority
providers = registry.list_by_category('metrics')

# List categories
categories = registry.list_categories()

# Render specific section
output = render_section(
    plugin_name='my_plugin',
    section_id='metrics',
    fmt=DisplayFormat.JSON,
    node=node_instance
)

# Collect all sections
all_data = collect_all_sections(fmt=DisplayFormat.JSON, node=node_instance)
```

---

## web_user HTTP API

### New Endpoints

#### GET /api/display/providers
Returns metadata about all registered display providers.

**Response:**
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
        "display_name": "ID Lease Metrics",
        "category": "metrics",
        "priority": 80,
        "refresh_interval_s": 5.0
      }
    ]
  }
}
```

#### GET /api/display/render/{plugin_name}:{section_id}?format=json
Render a specific display section.

**Query Parameters:**
- `format` - Output format: `json`, `html`, `text`, `table`, `tree` (default: `json`)

**Response:**
```json
{
  "ok": true,
  "section": "my_plugin:metrics",
  "format": "json",
  "data": { "metric1": 42, "metric2": 100 }
}
```

#### GET /api/display/all?format=json
Collect all registered display sections.

**Query Parameters:**
- `format` - Output format (default: `json`)

**Response:**
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

## tui Integration

### Dynamic Section Discovery

tui now automatically includes display provider sections in its section list:

```
| OpenSynaptic BIOS Console (with Display API Providers)
| Built-in Sections:
|   * 1. config
|   2. transport
|   3. pipeline
|   4. plugins
|   5. db
|   6. identity
| Display API Providers:
|   7. id_allocator:lease_metrics
|   8. test_plugin:performance
|   9. example_display:node_stats
```

### New Commands

- `[1-N]` - Switch to section by number (includes providers)
- `[m]` - Display metadata about all providers
- `[s]` - Search sections by partial name
- `[a]` - Show all sections (built-in + providers)
- `[r]` - Refresh current section
- `[j]` - Print current section as JSON
- `[auto N]` - Auto-refresh N cycles
- `[i SEC]` - Set refresh interval
- `[p]` - List available plugins
- `[h]` - Show help
- `[q]` - Quit

### Example Session

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
[displays section: id_allocator:lease_metrics]
```

---

## Example: Complete Plugin with Display Provider

File: `plugins/my_analytics_plugin.py`

```python
"""
Analytics Plugin with Display Provider.

Provides custom metrics visualization via Display API.
"""

from typing import Dict, Any
from opensynaptic.services.display_api import DisplayProvider, register_display_provider
import time


class AnalyticsMetricsDisplayProvider(DisplayProvider):
    """Display analytics metrics."""
    
    def __init__(self):
        super().__init__(
            plugin_name='my_analytics',
            section_id='metrics',
            display_name='Analytics Metrics'
        )
        self.category = 'metrics'
        self.priority = 85
        self.refresh_interval_s = 5.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        # Example: extract from node or any other source
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
            <h3>Analytics</h3>
            <ul>
                <li><strong>Total Requests:</strong> {data['requests_total']}</li>
                <li><strong>RPS:</strong> {data['requests_per_second']}</li>
                <li><strong>Errors:</strong> {data['errors']}</li>
                <li><strong>Avg Latency:</strong> {data['avg_latency_ms']:.1f}ms</li>
                <li><strong>P99 Latency:</strong> {data['p99_latency_ms']:.1f}ms</li>
            </ul>
        </div>
        """


class AnalyticsStatusDisplayProvider(DisplayProvider):
    """Display analytics system status."""
    
    def __init__(self):
        super().__init__(
            plugin_name='my_analytics',
            section_id='status',
            display_name='Analytics Status'
        )
        self.category = 'custom'
        self.priority = 70
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        return {
            'system_status': 'healthy',
            'backend_connected': True,
            'db_connected': True,
            'cache_size_mb': 512,
        }


def auto_load(config=None):
    """Register display providers when plugin loads."""
    register_display_provider(AnalyticsMetricsDisplayProvider())
    register_display_provider(AnalyticsStatusDisplayProvider())
    
    from opensynaptic.utils import os_log
    os_log.info(
        'MY_ANALYTICS',
        'DISPLAY_PROVIDERS_REGISTERED',
        'Analytics display providers registered',
        {'providers': ['metrics', 'status']}
    )
    
    return True
```

---

## Best Practices

1. **Keep extract_data() fast** - It's called frequently during refreshes
2. **Use appropriate categories** - 'metrics', 'core', 'transport', 'custom', etc.
3. **Set reasonable priorities** - Higher priority sections appear first
4. **Implement format methods selectively** - Only override what you need
5. **Return JSON-serializable data** - The JSON format is the default
6. **Handle missing node gracefully** - `node` may be None in some contexts
7. **Use consistent display names** - Make them user-friendly
8. **Test with both web_user and tui** - Ensure output is suitable for both UIs

---

## Testing Display Providers

### Command Line

```bash
# List all providers
python -u src/main.py example_display list

# Render specific section
python -u src/main.py example_display render example_display node_stats --format json

# Collect all sections
python -u src/main.py example_display collect --format json

# Render as HTML
python -u src/main.py example_display render my_plugin metrics --format html
```

### web_user

```bash
# View provider metadata
curl http://localhost:8765/api/display/providers

# Render specific section
curl http://localhost:8765/api/display/render/my_plugin:metrics?format=json

# Get all sections as HTML
curl http://localhost:8765/api/display/all?format=html
```

### tui

```bash
# Enter TUI and press 'm' to view provider metadata
python -u src/main.py tui interactive --section identity

# Inside BIOS, use 's' to search for sections
# Use '7', '8', '9', etc. to view provider sections
```

---

## Migration Guide: From Hardcoded to Display API

### Before (Hardcoded in tui)
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

### After (Display Provider)
```python
# In your plugin
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

Now tui and web_user automatically discover and render it without any hardcoding!

---

## Troubleshooting

**Provider not appearing in web_user or tui:**
- Check plugin is being loaded (visible in `plugin-test` or tui `[p]` command)
- Verify `register_display_provider()` is called in `auto_load()`
- Check registry with curl: `GET /api/display/providers`

**Error rendering section:**
- Check `extract_data()` doesn't raise exceptions
- Ensure returned data is JSON-serializable
- Check logs: search for `DISPLAY_RENDER_ERROR`

**HTML format not rendering properly:**
- Test in `curl`: `GET /api/display/render/plugin:section?format=html`
- Verify HTML is properly escaped
- Check browser console for rendering errors

**Performance issues:**
- Reduce refresh_interval_s in provider
- Optimize extract_data() to be faster
- Consider caching data within the provider

---

## See Also

- `src/opensynaptic/services/display_api.py` - Core DisplayAPI implementation
- `src/opensynaptic/services/example_display_plugin.py` - Reference examples
- `src/opensynaptic/services/tui/main.py` - tui integration
- `src/opensynaptic/services/web_user/main.py` - web_user integration
- `Config.json` - `expose_sections` configuration in web_user

