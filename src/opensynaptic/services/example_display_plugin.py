"""
Example Display Provider Plugin

This is a reference implementation showing how plugins can register custom
display sections that will be automatically discovered by web_user and tui.

To use:
1. Create a custom DisplayProvider subclass
2. Call register_display_provider() in your plugin's auto_load() or __init__()
3. web_user and tui will automatically discover and render your provider
"""

from typing import Any, Dict, List
import json
import time
from opensynaptic.services.display_api import (
    DisplayProvider,
    register_display_provider,
    DisplayFormat,
)


class NodeStatsDisplayProvider(DisplayProvider):
    """
    Example: Display device and node statistics.
    """
    
    def __init__(self):
        super().__init__(
            plugin_name='example_display',
            section_id='node_stats',
            display_name='Node Statistics'
        )
        self.category = 'core'
        self.priority = 80
        self.refresh_interval_s = 3.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        """Extract node-level statistics."""
        if not node:
            return {'error': 'No node provided'}
        
        data = {
            'device_id': getattr(node, 'device_id', 'UNKNOWN'),
            'assigned_id': getattr(node, 'assigned_id', None),
            'config_version': getattr(node, 'config', {}).get('VERSION', '?'),
            'active_transporters': sorted(list(getattr(node, 'active_transporters', {}).keys())),
            'uptime_seconds': getattr(node, '_uptime', 0),
        }
        return data
    
    def format_html(self, data: Dict[str, Any]) -> str:
        """Custom HTML formatting."""
        html = "<div style='padding: 10px; background: #f5f5f5; border-radius: 5px;'>"
        html += f"<h3>{self.display_name}</h3>"
        html += "<dl>"
        for k, v in data.items():
            if k != 'error':
                html += f"<dt><strong>{k}:</strong></dt><dd>{v}</dd>"
        html += "</dl></div>"
        return html
    
    def format_text(self, data: Dict[str, Any]) -> str:
        """Custom text formatting."""
        lines = [f"\n=== {self.display_name} ==="]
        for k, v in data.items():
            if k != 'error':
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)


class PipelineMetricsDisplayProvider(DisplayProvider):
    """
    Example: Display pipeline processing metrics.
    """
    
    def __init__(self):
        super().__init__(
            plugin_name='example_display',
            section_id='pipeline_metrics',
            display_name='Pipeline Metrics'
        )
        self.category = 'metrics'
        self.priority = 70
        self.refresh_interval_s = 5.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        """Extract pipeline metrics."""
        n = node or {}
        
        return {
            'standardizer_cache_entries': len(
                getattr(getattr(n, 'standardizer', None), 'registry', {})
            ),
            'engine_unit_symbols': len(
                getattr(getattr(n, 'engine', None), 'REV_UNIT', {})
            ),
            'fusion_cached_devices': len(
                getattr(getattr(n, 'fusion', None), '_RAM_CACHE', {})
            ),
            'fusion_template_total': sum(
                len(v.get('data', {}).get('templates', {}))
                for v in getattr(getattr(n, 'fusion', None), '_RAM_CACHE', {}).values()
            ),
            'timestamp': time.time(),
        }
    
    def format_table(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format as table rows."""
        return [{k: v for k, v in data.items() if k != 'timestamp'}]
    
    def format_text(self, data: Dict[str, Any]) -> str:
        """Custom text formatting."""
        lines = [f"\n{'Metric':<30} {'Value':>15}"]
        lines.append("-" * 47)
        for k, v in data.items():
            if k != 'timestamp':
                lines.append(f"{k:<30} {str(v):>15}")
        return "\n".join(lines)


class TransportStatusDisplayProvider(DisplayProvider):
    """
    Example: Display transporter status.
    """
    
    def __init__(self):
        super().__init__(
            plugin_name='example_display',
            section_id='transport_status',
            display_name='Transport Status'
        )
        self.category = 'transport'
        self.priority = 75
        self.refresh_interval_s = 2.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        """Extract transport status."""
        cfg = getattr(node, 'config', {}) if node else {}
        res = cfg.get('RESOURCES', {})
        
        return {
            'active': sorted(list(getattr(node, 'active_transporters', {}).keys())) if node else [],
            'l4_protocols': res.get('transport_status', {}),
            'phy_protocols': res.get('physical_status', {}),
            'app_protocols': res.get('application_status', {}),
        }
    
    def format_html(self, data: Dict[str, Any]) -> str:
        """Custom HTML formatting."""
        html = "<div style='padding: 10px; background: #fff9e6; border-radius: 5px;'>"
        html += f"<h4>{self.display_name}</h4>"
        html += "<ul>"
        
        for proto in data.get('active', []):
            html += f"<li><strong>{proto}</strong> ✓</li>"
        
        html += "</ul></div>"
        return html


class CustomSectionDisplayProvider(DisplayProvider):
    """
    Template: Extend this class to add your own custom display section.
    """
    
    def __init__(self, plugin_name='my_plugin', section_id='my_section'):
        super().__init__(
            plugin_name=plugin_name,
            section_id=section_id,
            display_name=f'{plugin_name}: {section_id}'
        )
        # Customize these attributes:
        self.category = 'custom'
        self.priority = 50
        self.refresh_interval_s = 2.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        """
        TODO: Implement data extraction logic.
        
        Return a dict with your custom data structure.
        The dict should be JSON-serializable by default.
        """
        return {
            'placeholder': 'Implement extract_data() to fetch your data',
            'example_key': 'example_value',
        }


# ============================================================================
#  Plugin Auto-Load Function
# ============================================================================

def auto_load(config=None):
    """
    Auto-load function called when the plugin is mounted.
    Registers all display providers.
    """
    # Register example display providers
    register_display_provider(NodeStatsDisplayProvider())
    register_display_provider(PipelineMetricsDisplayProvider())
    register_display_provider(TransportStatusDisplayProvider())
    
    from opensynaptic.utils import os_log
    os_log.info(
        'DISPLAY_PROVIDER',
        'AUTO_LOAD',
        'Example display providers registered',
        {
            'providers': [
                'node_stats',
                'pipeline_metrics',
                'transport_status'
            ]
        }
    )
    
    return True


# ============================================================================
#  CLI Integration (Optional)
# ============================================================================

def get_cli_commands():
    """Expose CLI commands for display provider testing."""
    from opensynaptic.services.display_api import (
        get_display_registry,
        render_section,
        DisplayFormat,
        collect_all_sections,
    )
    
    def _list_providers(argv):
        """List all registered display providers."""
        registry = get_display_registry()
        metadata = registry.get_metadata()
        print(json.dumps(metadata, indent=2))
        return 0
    
    def _render(argv):
        """Render a specific display section."""
        import argparse
        p = argparse.ArgumentParser(prog='example_display render')
        p.add_argument('plugin', help='Plugin name')
        p.add_argument('section', help='Section ID')
        p.add_argument('--format', default='json', 
                      choices=['json', 'text', 'html', 'table', 'tree'])
        ns = p.parse_args(argv)
        
        fmt = DisplayFormat[ns.format.upper()]
        # Note: This is a simple demo; in real use you'd pass the node
        output = render_section(ns.plugin, ns.section, fmt, node=None)
        
        if output is None:
            print(f"ERROR: No provider found: {ns.plugin}:{ns.section}")
            return 1
        
        if isinstance(output, str):
            print(output)
        else:
            print(json.dumps(output, indent=2, default=str))
        return 0
    
    def _collect_all(argv):
        """Collect all registered display sections."""
        import argparse
        p = argparse.ArgumentParser(prog='example_display collect')
        p.add_argument('--format', default='json',
                      choices=['json', 'text', 'html', 'table', 'tree'])
        ns = p.parse_args(argv)
        
        fmt = DisplayFormat[ns.format.upper()]
        output = collect_all_sections(fmt=fmt, node=None)
        
        if isinstance(output, str):
            print(output)
        else:
            print(json.dumps(output, indent=2, default=str))
        return 0
    
    return {
        'list': _list_providers,
        'render': _render,
        'collect': _collect_all,
    }

