"""
Display API Standard for Self-Discoverable Visualization

This module defines a standard interface for plugins to register custom display sections
that can be automatically discovered and rendered by web_user and tui.

Architecture:
- Plugins register display providers via DisplayRegistry
- Each provider defines how to extract/format data for a specific view
- web_user and tui auto-discover and call providers to generate visualizations
- Providers can support multiple output formats (json, html, text, table)
"""

import abc
import threading
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class DisplayFormat(Enum):
    """Supported output formats for display providers."""
    JSON = "json"          # Dict/list suitable for JSON serialization
    HTML = "html"          # HTML string for web rendering
    TEXT = "text"          # Plain text for terminal output
    TABLE = "table"        # Tabular data (list of dicts or 2D array)
    TREE = "tree"          # Hierarchical/tree structure


class DisplayProvider(abc.ABC):
    """
    Abstract base class for display providers.
    
    A display provider handles extraction and formatting of data for a specific
    visualization section. Plugins should subclass this to provide custom displays.
    """
    
    def __init__(self, plugin_name: str, section_id: str, display_name: str = None):
        """
        Initialize a display provider.
        
        Args:
            plugin_name: Name of the plugin providing this display (e.g., 'my_plugin')
            section_id: Unique identifier for this display section (e.g., 'metrics_summary')
            display_name: Human-readable display name (defaults to section_id)
        """
        self.plugin_name = str(plugin_name).strip()
        self.section_id = str(section_id).strip()
        self.display_name = str(display_name or section_id).strip()
        self.category = "plugin"  # Can be overridden by subclasses
        self.priority = 50  # Display priority (0-100, higher = first)
        self.refresh_interval_s = 2.0  # Suggested refresh interval
        # Frontend hint: safe_html (default), trusted_html, or json_only.
        self.render_mode = "safe_html"
        
    @abc.abstractmethod
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        """
        Extract and prepare data for display.
        
        Args:
            node: Reference to the OpenSynaptic node
            **kwargs: Additional context/filters from caller
            
        Returns:
            Dict containing the extracted data
        """
        pass
    
    def format_json(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format data as JSON-serializable dict.
        Default: return data as-is.
        
        Args:
            data: Output from extract_data()
            
        Returns:
            JSON-serializable dict
        """
        return data
    
    def format_html(self, data: Dict[str, Any]) -> str:
        """
        Format data as HTML string for web display.
        Default: generates basic HTML table from data.
        
        Args:
            data: Output from extract_data()
            
        Returns:
            HTML string
        """
        return self._default_html_table(data)
    
    def format_text(self, data: Dict[str, Any]) -> str:
        """
        Format data as plain text for terminal display.
        Default: pretty-print as JSON.
        
        Args:
            data: Output from extract_data()
            
        Returns:
            Plain text string
        """
        import json
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)
    
    def format_table(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Format data as tabular structure.
        Default: wrap data items in list.
        
        Args:
            data: Output from extract_data()
            
        Returns:
            List of dicts (rows) or 2D array
        """
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []
    
    def format_tree(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format data as hierarchical tree structure.
        Default: return data as-is (assumed to be tree-shaped).
        
        Args:
            data: Output from extract_data()
            
        Returns:
            Tree-structured dict
        """
        return data
    
    @staticmethod
    def _default_html_table(data: Dict[str, Any]) -> str:
        """Generate a basic HTML table from dict data."""
        rows = []
        rows.append("<table border='1' cellpadding='5' cellspacing='0' style='border-collapse:collapse'>")
        
        if isinstance(data, dict):
            for key, value in data.items():
                safe_key = str(key).replace('<', '&lt;').replace('>', '&gt;')
                safe_val = str(value).replace('<', '&lt;').replace('>', '&gt;')
                rows.append(f"<tr><td><strong>{safe_key}</strong></td><td>{safe_val}</td></tr>")
        elif isinstance(data, list):
            # List of dicts
            if data and isinstance(data[0], dict):
                keys = list(data[0].keys())
                rows.append("<tr>" + "".join(f"<th>{k}</th>" for k in keys) + "</tr>")
                for item in data:
                    row_html = "".join(
                        f"<td>{str(item.get(k, '')).replace('<', '&lt;').replace('>', '&gt;')}</td>"
                        for k in keys
                    )
                    rows.append(f"<tr>{row_html}</tr>")
        
        rows.append("</table>")
        return "\n".join(rows)
    
    def supports_format(self, fmt: DisplayFormat) -> bool:
        """
        Check if this provider supports a particular format.
        Override to restrict formats.
        
        Args:
            fmt: DisplayFormat enum value
            
        Returns:
            True if format is supported
        """
        return True


class DisplayRegistry:
    """
    Global registry for display providers.
    
    Plugins register their display providers here so that web_user and tui
    can auto-discover and call them.
    """
    
    def __init__(self):
        self._lock = threading.RLock()
        self._providers: Dict[str, DisplayProvider] = {}  # key: "{plugin_name}:{section_id}"
        self._categories: Dict[str, List[str]] = {}  # category -> [provider_keys]
    
    def register(self, provider: DisplayProvider) -> bool:
        """
        Register a display provider.
        
        Args:
            provider: DisplayProvider instance
            
        Returns:
            True if registered successfully, False if duplicate
        """
        with self._lock:
            key = f"{provider.plugin_name}:{provider.section_id}"
            if key in self._providers:
                return False
            
            self._providers[key] = provider
            
            category = getattr(provider, 'category', 'plugin')
            if category not in self._categories:
                self._categories[category] = []
            self._categories[category].append(key)
            
            return True
    
    def unregister(self, plugin_name: str, section_id: str) -> bool:
        """
        Unregister a display provider.
        
        Args:
            plugin_name: Plugin name
            section_id: Section ID
            
        Returns:
            True if unregistered, False if not found
        """
        with self._lock:
            key = f"{plugin_name}:{section_id}"
            if key not in self._providers:
                return False
            
            provider = self._providers.pop(key)
            category = getattr(provider, 'category', 'plugin')
            if category in self._categories:
                try:
                    self._categories[category].remove(key)
                except ValueError:
                    pass
            
            return True
    
    def get(self, plugin_name: str, section_id: str) -> Optional[DisplayProvider]:
        """
        Retrieve a specific display provider.
        
        Args:
            plugin_name: Plugin name
            section_id: Section ID
            
        Returns:
            DisplayProvider or None
        """
        with self._lock:
            key = f"{plugin_name}:{section_id}"
            return self._providers.get(key)
    
    def list_all(self) -> List[Tuple[str, DisplayProvider]]:
        """
        List all registered display providers, sorted by priority.
        
        Returns:
            List of (key, provider) tuples sorted by priority (descending)
        """
        with self._lock:
            items = list(self._providers.items())
        
        # Sort by priority (descending) then by key
        items.sort(key=lambda x: (-getattr(x[1], 'priority', 50), x[0]))
        return items
    
    def list_by_category(self, category: str) -> List[Tuple[str, DisplayProvider]]:
        """
        List providers in a specific category.
        
        Args:
            category: Category name
            
        Returns:
            List of (key, provider) tuples
        """
        with self._lock:
            keys = self._categories.get(category, [])
            items = [(k, self._providers[k]) for k in keys if k in self._providers]
        
        items.sort(key=lambda x: (-getattr(x[1], 'priority', 50), x[0]))
        return items
    
    def list_categories(self) -> List[str]:
        """List all registered categories."""
        with self._lock:
            return sorted(list(self._categories.keys()))
    
    def get_metadata(self, plugin_name: str = None) -> Dict[str, Any]:
        """
        Get metadata about registered providers.
        
        Args:
            plugin_name: Filter by plugin name (None = all)
            
        Returns:
            Metadata dict
        """
        with self._lock:
            items = list(self._providers.items())
        
        result: Dict[str, Any] = {
            'total_providers': len(items),
            'categories': self.list_categories(),
            'providers': []
        }
        providers_meta: List[Dict[str, Any]] = result['providers']
        
        for key, provider in items:
            pname, sid = key.split(':', 1)
            if plugin_name and pname != plugin_name:
                continue
            supported_formats = []
            for fmt in DisplayFormat:
                try:
                    if bool(provider.supports_format(fmt)):
                        supported_formats.append(fmt.value)
                except Exception:
                    continue
            if not supported_formats:
                supported_formats = ['json']
            preferred = str(getattr(provider, 'preferred_format', '') or '').strip().lower()
            if preferred not in supported_formats:
                for candidate in ('html', 'table', 'json', 'text', 'tree'):
                    if candidate in supported_formats:
                        preferred = candidate
                        break
            if not preferred:
                preferred = 'json'
            render_mode = str(getattr(provider, 'render_mode', 'safe_html') or 'safe_html').strip().lower()
            if render_mode not in ('safe_html', 'trusted_html', 'json_only'):
                render_mode = 'safe_html'
            
            providers_meta.append({
                'plugin_name': pname,
                'section_id': sid,
                'section_path': key,
                'display_name': getattr(provider, 'display_name', sid),
                'category': getattr(provider, 'category', 'plugin'),
                'priority': getattr(provider, 'priority', 50),
                'refresh_interval_s': getattr(provider, 'refresh_interval_s', 2.0),
                'supported_formats': supported_formats,
                'preferred_format': preferred,
                'render_mode': render_mode,
            })
        
        return result


# Global display registry singleton
_DISPLAY_REGISTRY = DisplayRegistry()


def get_display_registry() -> DisplayRegistry:
    """Get the global display registry."""
    return _DISPLAY_REGISTRY


def register_display_provider(provider: DisplayProvider) -> bool:
    """
    Register a display provider globally.
    
    Args:
        provider: DisplayProvider instance
        
    Returns:
        True if registered successfully
    """
    return _DISPLAY_REGISTRY.register(provider)


def render_section(plugin_name: str, section_id: str, fmt: DisplayFormat,
                   node=None, **kwargs) -> Optional[Any]:
    """
    Render a display section in the specified format.
    
    Args:
        plugin_name: Plugin name
        section_id: Section ID
        fmt: DisplayFormat enum value
        node: OpenSynaptic node reference
        **kwargs: Additional context for provider
        
    Returns:
        Formatted output (type depends on DisplayFormat)
    """
    provider = _DISPLAY_REGISTRY.get(plugin_name, section_id)
    if not provider:
        return None
    
    try:
        data = provider.extract_data(node=node, **kwargs)
        
        if fmt == DisplayFormat.JSON:
            return provider.format_json(data)
        elif fmt == DisplayFormat.HTML:
            return provider.format_html(data)
        elif fmt == DisplayFormat.TEXT:
            return provider.format_text(data)
        elif fmt == DisplayFormat.TABLE:
            return provider.format_table(data)
        elif fmt == DisplayFormat.TREE:
            return provider.format_tree(data)
        else:
            return data
    except Exception as e:
        from opensynaptic.utils import os_log
        os_log.err('DISPLAY_API', 'RENDER_FAILED', e, {
            'plugin': plugin_name,
            'section': section_id,
            'format': fmt.value
        })
        return None


def collect_all_sections(fmt: DisplayFormat = DisplayFormat.JSON,
                         node=None, **kwargs) -> Dict[str, Any]:
    """
    Collect rendered output from all registered display providers.
    
    Args:
        fmt: DisplayFormat enum value
        node: OpenSynaptic node reference
        **kwargs: Additional context
        
    Returns:
        Dict with structure: {category: {section_id: output}, ...}
    """
    result = {}
    
    for key, provider in _DISPLAY_REGISTRY.list_all():
        plugin_name, section_id = key.split(':', 1)
        category = getattr(provider, 'category', 'plugin')
        
        if category not in result:
            result[category] = {}
        
        output = render_section(plugin_name, section_id, fmt, node=node, **kwargs)
        if output is not None:
            result[category][section_id] = output
    
    return result


# ============================================================================
#  Auto-Load Built-in Display Providers
# ============================================================================
# When this module is imported, automatically load the built-in display
# providers so they're available without explicit registration.

def _auto_load_builtin_providers():
    """Auto-load built-in display providers."""
    try:
        from opensynaptic.services.builtin_display_providers import auto_load_builtin_providers
        auto_load_builtin_providers()
    except Exception as e:
        # Fail silently - builtin providers are optional
        pass


_auto_load_builtin_providers()

