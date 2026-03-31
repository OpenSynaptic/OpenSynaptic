"""
Built-in Display Providers for web_user and tui

This module provides the core display providers that replace hardcoded
section rendering in web_user and tui. By moving these to Display Providers,
we can dramatically simplify web_user and tui code.

These providers are automatically registered when the display API is imported.
"""

from typing import Dict, Any
from opensynaptic.services.display_api import DisplayProvider, register_display_provider
import time


class IdentityDisplayProvider(DisplayProvider):
    """Display device identity and version information."""
    
    def __init__(self):
        super().__init__(
            plugin_name='opensynaptic_core',
            section_id='identity',
            display_name='Device Identity'
        )
        self.category = 'core'
        self.priority = 100
        self.refresh_interval_s = 10.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        if not node:
            return {'error': 'Node not available'}
        
        cfg = getattr(node, 'config', {})
        return {
            'device_id': getattr(node, 'device_id', 'UNKNOWN'),
            'assigned_id': getattr(node, 'assigned_id', None),
            'version': cfg.get('VERSION', '?'),
            'timestamp': int(time.time()),
        }


class ConfigDisplayProvider(DisplayProvider):
    """Display configuration settings."""
    
    def __init__(self):
        super().__init__(
            plugin_name='opensynaptic_core',
            section_id='config',
            display_name='Configuration'
        )
        self.category = 'core'
        self.priority = 95
        self.refresh_interval_s = 5.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        cfg = getattr(node, 'config', {}) if node else {}
        return {
            'engine_settings': cfg.get('engine_settings', {}),
            'payload_switches': cfg.get('payload_switches', {}),
            'opensynaptic_setting': cfg.get('OpenSynaptic_Setting', {}),
            'security_settings': cfg.get('security_settings', {}),
            'timestamp': int(time.time()),
        }


class TransportDisplayProvider(DisplayProvider):
    """Display transporter status and configuration."""
    
    def __init__(self):
        super().__init__(
            plugin_name='opensynaptic_core',
            section_id='transport',
            display_name='Transport Status'
        )
        self.category = 'core'
        self.priority = 90
        self.refresh_interval_s = 3.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        cfg = getattr(node, 'config', {}) if node else {}
        res = cfg.get('RESOURCES', {})
        
        return {
            'active_transporters': sorted(list(getattr(node, 'active_transporters', {}).keys())) if node else [],
            'transporters_status': res.get('transporters_status', {}),
            'transport_status': res.get('transport_status', {}),
            'physical_status': res.get('physical_status', {}),
            'application_status': res.get('application_status', {}),
            'timestamp': int(time.time()),
        }


class PipelineDisplayProvider(DisplayProvider):
    """Display pipeline processing status and metrics."""
    
    def __init__(self):
        super().__init__(
            plugin_name='opensynaptic_core',
            section_id='pipeline',
            display_name='Pipeline Metrics'
        )
        self.category = 'core'
        self.priority = 85
        self.refresh_interval_s = 2.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        if not node:
            return {'error': 'Node not available'}
        
        n = node
        fusion = getattr(n, 'fusion', None)
        ram_cache = getattr(fusion, '_RAM_CACHE', {}) if fusion else {}
        
        return {
            'standardizer_cache_entries': len(getattr(getattr(n, 'standardizer', None), 'registry', {})),
            'engine_rev_unit_entries': len(getattr(getattr(n, 'engine', None), 'REV_UNIT', {})),
            'fusion_ram_cache_aids': list(ram_cache.keys()),
            'fusion_template_count': sum(
                len(v.get('data', {}).get('templates', {}))
                for v in ram_cache.values()
            ),
            'timestamp': int(time.time()),
        }


class PluginsDisplayProvider(DisplayProvider):
    """Display loaded plugins and service status."""
    
    def __init__(self):
        super().__init__(
            plugin_name='opensynaptic_core',
            section_id='plugins',
            display_name='Plugins Status'
        )
        self.category = 'core'
        self.priority = 80
        self.refresh_interval_s = 3.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        if not node or not hasattr(node, 'service_manager'):
            return {'mount_index': [], 'runtime_index': {}}
        
        snap = node.service_manager.snapshot()
        return {
            'mount_index': snap.get('mount_index', []),
            'runtime_index': snap.get('runtime_index', {}),
            'timestamp': int(time.time()),
        }


class DatabaseDisplayProvider(DisplayProvider):
    """Display database connection status."""
    
    def __init__(self):
        super().__init__(
            plugin_name='opensynaptic_core',
            section_id='db',
            display_name='Database Status'
        )
        self.category = 'core'
        self.priority = 75
        self.refresh_interval_s = 5.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        if not node:
            return {'enabled': False}
        
        db = getattr(node, 'db_manager', None)
        return {
            'enabled': bool(db),
            'dialect': getattr(db, 'dialect', None),
            'timestamp': int(time.time()),
        }


def auto_load_builtin_providers(config=None):
    """Register all built-in display providers."""
    register_display_provider(IdentityDisplayProvider())
    register_display_provider(ConfigDisplayProvider())
    register_display_provider(TransportDisplayProvider())
    register_display_provider(PipelineDisplayProvider())
    register_display_provider(PluginsDisplayProvider())
    register_display_provider(DatabaseDisplayProvider())
    
    return True


# Auto-register on import
auto_load_builtin_providers()

