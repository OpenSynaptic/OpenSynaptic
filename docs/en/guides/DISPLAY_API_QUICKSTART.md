Display API Quick Start Guide
=============================

## What Changed?

The web_user and tui no longer have hardcoded display sections. Instead, they auto-discover "Display Providers" registered by plugins. This makes it easy for any plugin to contribute custom visualization without modifying core code.

## 5-Minute Quickstart

### 1. Create a Display Provider

In your plugin file, add a display provider class:

```python
from opensynaptic.services.display_api import DisplayProvider, register_display_provider

class MyMetricsDisplay(DisplayProvider):
    def __init__(self):
        super().__init__(
            plugin_name='my_plugin',
            section_id='metrics',
            display_name='My Metrics'
        )
    
    def extract_data(self, node=None, **kwargs):
        return {
            'value1': 42,
            'value2': 100,
            'status': 'healthy'
        }

def auto_load(config=None):
    register_display_provider(MyMetricsDisplay())
    return True
```

### 2. Access via web_user

```bash
# Get all providers
curl http://localhost:8765/api/display/providers

# Render your section
curl http://localhost:8765/api/display/render/my_plugin:metrics

# Get all sections from all providers
curl http://localhost:8765/api/display/all
```

### 3. Access via tui

```bash
# In BIOS console
bios> m              # View provider metadata
bios> s metrics      # Search for sections
bios> 7              # Switch to section 7 (your new section)
bios> j              # View as JSON
```

## Key Files

| File | Purpose |
|------|---------|
| `src/opensynaptic/services/display_api.py` | Core Display API implementation |
| `src/opensynaptic/services/example_display_plugin.py` | Reference examples |
| `src/opensynaptic/services/tui/main.py` | tui integration (updated) |
| `src/opensynaptic/services/web_user/main.py` | web_user integration (updated) |
| `src/opensynaptic/services/web_user/handlers.py` | New HTTP endpoints (updated) |
| `DISPLAY_API_GUIDE.md` | Complete documentation |

## Quick Reference: DisplayProvider API

### Create Provider
```python
class MyProvider(DisplayProvider):
    def __init__(self):
        super().__init__(
            plugin_name='my_plugin',
            section_id='my_section',
            display_name='Display Name'
        )
        self.category = 'metrics'           # 'metrics', 'core', 'custom', etc.
        self.priority = 75                  # 0-100, higher = shown first
        self.refresh_interval_s = 5.0       # Suggested refresh rate
    
    def extract_data(self, node=None, **kwargs):
        # Return dict with your data
        return {'key': 'value'}
    
    # Optional: customize formatting
    def format_html(self, data):
        return "<div>custom html</div>"
```

### Register Provider
```python
from opensynaptic.services.display_api import register_display_provider

def auto_load(config=None):
    register_display_provider(MyProvider())
    return True
```

### Output Formats

Your provider can support these formats automatically:
- **JSON** - Dict, default `format_json()`
- **HTML** - HTML string, default generates table
- **TEXT** - Plain text, default pretty-prints JSON
- **TABLE** - List of dicts/2D array, default wraps in list
- **TREE** - Hierarchical dict, default returns as-is

## Web API Endpoints

### GET /api/display/providers
Get metadata about all registered providers
```json
{"ok": true, "metadata": {...}}
```

### GET /api/display/render/{plugin}:{section}?format=json
Render a specific section
```json
{"ok": true, "section": "plugin:section", "format": "json", "data": {...}}
```

### GET /api/display/all?format=json
Get all sections from all providers
```json
{"ok": true, "format": "json", "sections": {...}, "timestamp": ...}
```

## TUI Commands

| Command | Description |
|---------|-------------|
| `1-N` | Switch to numbered section (includes providers) |
| `a` | Show all sections |
| `r` | Refresh current section |
| `j` | Print as JSON |
| `m` | Show provider metadata |
| `s` | Search for section |
| `p` | List plugins |
| `auto N` | Auto-refresh N cycles |
| `i SEC` | Set refresh interval |
| `h` | Show help |
| `q` | Quit |

## Example: ID Allocator Plugin

If the id_allocator plugin registers a display provider:

```python
# In id_allocator.py
class IDLeaseMetricsDisplay(DisplayProvider):
    def __init__(self):
        super().__init__('id_allocator', 'lease_metrics', 'ID Lease Metrics')
        self.category = 'metrics'
        self.priority = 80
    
    def extract_data(self, node=None, **kwargs):
        # Access node to get data
        allocator = getattr(node, 'id_allocator', None)
        return {
            'total_allocated': allocator.total_allocated,
            'active_ids': len(allocator.active_ids),
            'effective_lease_seconds': allocator.effective_lease_seconds,
        }
```

Then:
1. **web_user**: `GET /api/display/render/id_allocator:lease_metrics`
2. **tui**: Type section number to view the metrics
3. **No hardcoding needed!**

## Testing Your Provider

### Option 1: Using CLI
```bash
python -u src/main.py example_display list
python -u src/main.py example_display render my_plugin my_section --format json
```

### Option 2: Using web_user
```bash
# Start web_user
python -u src/main.py web_user start &

# Test endpoints
curl http://localhost:8765/api/display/providers
curl http://localhost:8765/api/display/render/my_plugin:my_section
```

### Option 3: Using tui
```bash
python -u src/main.py tui interactive
# In BIOS, press 'm' to see all providers
```

## Common Patterns

### Metric Display
```python
class MetricsProvider(DisplayProvider):
    def __init__(self):
        super().__init__('metrics_plugin', 'perf', 'Performance')
        self.category = 'metrics'
        self.priority = 85
    
    def extract_data(self, node=None, **kwargs):
        return {'cpu': 45.2, 'memory': 78.5, 'disk': 60.0}
    
    def format_html(self, data):
        bars = ''.join(f"<div>{k}: {'▓'*int(v/10)}{'░'*int((100-v)/10)}</div>"
                       for k, v in data.items())
        return f"<div style='font-family:monospace'>{bars}</div>"
```

### Status Display
```python
class StatusProvider(DisplayProvider):
    def __init__(self):
        super().__init__('status_plugin', 'health', 'Health Status')
        self.category = 'core'
        self.priority = 90
    
    def extract_data(self, node=None, **kwargs):
        return {
            'transport': 'healthy' if node.is_transport_ready else 'down',
            'database': 'connected' if node.db_ready else 'error',
            'uptime_s': node.uptime_seconds,
        }
```

### Config Display
```python
class ConfigProvider(DisplayProvider):
    def __init__(self):
        super().__init__('config_plugin', 'active', 'Active Config')
        self.category = 'core'
    
    def extract_data(self, node=None, **kwargs):
        cfg = node.config if node else {}
        return {
            'core_backend': cfg.get('engine_settings', {}).get('core_backend'),
            'precision': cfg.get('engine_settings', {}).get('precision'),
            'compression_enabled': cfg.get('engine_settings', {}).get('active_compression'),
        }
```

## Benefits

✅ **No Hardcoding** - Plugins define their own displays
✅ **Auto-Discovery** - web_user and tui discover all providers
✅ **Flexible** - Support JSON, HTML, text, table, tree formats
✅ **Extensible** - Add new providers without touching core code
✅ **Unified** - Single API for web and terminal UIs
✅ **Easy Testing** - Test via CLI, web, or tui

## See Also

- **Full Guide**: `DISPLAY_API_GUIDE.md`
- **Reference Implementation**: `src/opensynaptic/services/example_display_plugin.py`
- **Core Module**: `src/opensynaptic/services/display_api.py`

