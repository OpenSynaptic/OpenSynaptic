"""
ID Allocator Display Provider Plugin

This is a realistic example of how the id_allocator plugin would register
custom display providers to show ID lease metrics and status information.

To integrate with an existing plugin, add this code to the plugin's auto_load():

    from opensynaptic.services.display_api import register_display_provider
    
    register_display_provider(IDLeaseMetricsDisplay())
    register_display_provider(IDAllocationStatusDisplay())
"""

from typing import Dict, Any
from opensynaptic.services.display_api import DisplayProvider, register_display_provider
import time


class IDLeaseMetricsDisplay(DisplayProvider):
    """
    Display ID lease system metrics.
    
    Shows current lease configuration and adaptive policy metrics:
    - Base lease duration
    - Effective lease (after adaptive policy)
    - New device rate
    - Ultra-rate status
    """
    
    def __init__(self):
        super().__init__(
            plugin_name='id_allocator',
            section_id='lease_metrics',
            display_name='ID Lease Metrics'
        )
        self.category = 'metrics'
        self.priority = 85
        self.refresh_interval_s = 5.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        """Extract ID lease metrics from node."""
        if not node:
            return {'error': 'Node not available'}
        
        # Try to get id_allocator from node
        allocator = getattr(node, 'id_allocator', None)
        if not allocator:
            return {
                'status': 'id_allocator not loaded',
                'timestamp': int(time.time()),
            }
        
        # Extract configuration
        cfg = getattr(node, 'config', {})
        lease_cfg = ((cfg.get('security_settings', {}) or {}).get('id_lease', {}) or {})
        
        return {
            'status': 'active',
            'configuration': {
                'base_lease_seconds': int(lease_cfg.get('base_lease_seconds', 2592000)),
                'offline_hold_days': int(lease_cfg.get('offline_hold_days', 30)),
                'min_lease_seconds': int(lease_cfg.get('min_lease_seconds', 0)),
                'adaptive_enabled': bool(lease_cfg.get('adaptive_enabled', True)),
                'ultra_force_release': bool(lease_cfg.get('ultra_force_release', True)),
            },
            'metrics': {
                'effective_lease_seconds': int(getattr(allocator, 'effective_lease_seconds', 2592000)),
                'new_device_rate_per_hour': float(getattr(allocator, 'new_device_rate_per_hour', 0.0)),
                'ultra_rate_active': bool(getattr(allocator, 'ultra_rate_active', False)),
                'force_zero_lease_active': bool(getattr(allocator, 'force_zero_lease_active', False)),
                'total_reclaimed': int(getattr(allocator, 'total_reclaimed', 0)),
            },
            'thresholds': {
                'high_rate_threshold_per_hour': int(lease_cfg.get('high_rate_threshold_per_hour', 60)),
                'ultra_rate_threshold_per_hour': int(lease_cfg.get('ultra_rate_threshold_per_hour', 180)),
                'ultra_rate_sustain_seconds': int(lease_cfg.get('ultra_rate_sustain_seconds', 600)),
            },
            'timestamp': int(time.time()),
        }
    
    def format_html(self, data: Dict[str, Any]) -> str:
        """Custom HTML rendering with color coding."""
        if 'error' in data:
            return f"<div style='color: red; padding: 10px;'>{data['error']}</div>"
        
        metrics = data.get('metrics', {})
        cfg = data.get('configuration', {})
        
        # Color code the status
        ultra_active = metrics.get('ultra_rate_active', False)
        status_color = '#ff6b6b' if ultra_active else '#51cf66'
        status_text = '🔴 ULTRA RATE' if ultra_active else '🟢 NORMAL'
        
        html = f"""
        <div style="padding: 12px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    border-radius: 8px; color: white; font-family: monospace;">
            <h3 style="margin: 0 0 10px 0;">📊 ID Lease Metrics</h3>
            
            <div style="background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px; margin-bottom: 10px;">
                <div><strong>Status:</strong> <span style="color: {status_color};">{status_text}</span></div>
                <div><strong>Base Lease:</strong> {cfg.get('base_lease_seconds', 0):,} seconds ({cfg.get('offline_hold_days', 0)} days)</div>
                <div><strong>Effective Lease:</strong> {metrics.get('effective_lease_seconds', 0):,} seconds</div>
            </div>
            
            <div style="background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px; margin-bottom: 10px;">
                <div><strong>New Device Rate:</strong> {metrics.get('new_device_rate_per_hour', 0):.1f} devices/hour</div>
                <div><strong>High-Rate Threshold:</strong> {data.get('thresholds', {}).get('high_rate_threshold_per_hour', 60)}/hour</div>
                <div><strong>Ultra-Rate Threshold:</strong> {data.get('thresholds', {}).get('ultra_rate_threshold_per_hour', 180)}/hour</div>
            </div>
            
            <div style="background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px;">
                <div><strong>Adaptive:</strong> {'Enabled ✓' if cfg.get('adaptive_enabled') else 'Disabled'}</div>
                <div><strong>Force-Zero Lease:</strong> {'Active ⚡' if metrics.get('force_zero_lease_active') else 'Inactive'}</div>
                <div><strong>IDs Reclaimed:</strong> {metrics.get('total_reclaimed', 0)}</div>
            </div>
        </div>
        """
        return html
    
    def format_text(self, data: Dict[str, Any]) -> str:
        """ASCII art text rendering for terminal."""
        if 'error' in data:
            return f"ERROR: {data['error']}"
        
        metrics = data.get('metrics', {})
        cfg = data.get('configuration', {})
        ultra_active = metrics.get('ultra_rate_active', False)
        
        lines = [
            "",
            "╔════════════════════════════════════════╗",
            "║     ID Lease Metrics                   ║",
            "╠════════════════════════════════════════╣",
            f"║ Status: {'🔴 ULTRA RATE' if ultra_active else '🟢 NORMAL':30} │",
            "╠════════════════════════════════════════╣",
            f"║ Base Lease:    {cfg.get('base_lease_seconds', 0):>24} sec │",
            f"║ Effective:     {metrics.get('effective_lease_seconds', 0):>24} sec │",
            f"║ Device Rate:   {metrics.get('new_device_rate_per_hour', 0):>24.1f} /hr │",
            "╠════════════════════════════════════════╣",
            f"║ Adaptive:      {'Enabled ✓' if cfg.get('adaptive_enabled') else 'Disabled':28} │",
            f"║ Force-Zero:    {'Active ⚡' if metrics.get('force_zero_lease_active') else 'Inactive':28} │",
            f"║ Reclaimed:     {metrics.get('total_reclaimed', 0):>24} │",
            "╚════════════════════════════════════════╝",
            ""
        ]
        return "\n".join(lines)


class IDAllocationStatusDisplay(DisplayProvider):
    """
    Display ID allocation pool status.
    
    Shows:
    - Total allocated IDs
    - Available IDs
    - Recently expired (reclaimed) IDs
    - Pending offline IDs
    """
    
    def __init__(self):
        super().__init__(
            plugin_name='id_allocator',
            section_id='allocation_status',
            display_name='ID Allocation Status'
        )
        self.category = 'core'
        self.priority = 75
        self.refresh_interval_s = 3.0
    
    def extract_data(self, node=None, **kwargs) -> Dict[str, Any]:
        """Extract ID allocation status."""
        if not node:
            return {'error': 'Node not available'}
        
        allocator = getattr(node, 'id_allocator', None)
        if not allocator:
            return {'status': 'id_allocator not loaded'}
        
        # Mock data structure (would be actual allocator state)
        total_available = 4294967295 - 1  # MAX_UINT32 excluding sentinel
        allocated = getattr(allocator, 'allocated_count', 0)
        available = total_available - allocated
        released = getattr(allocator, 'released_count', 0)
        offline = getattr(allocator, 'offline_count', 0)
        
        return {
            'status': 'healthy',
            'pool_info': {
                'total_available': total_available,
                'allocated': allocated,
                'available': available,
                'released': released,
                'offline': offline,
            },
            'utilization_percent': (allocated / total_available * 100) if total_available > 0 else 0,
            'recent_activity': {
                'allocations_last_hour': getattr(allocator, 'alloc_count_last_hour', 0),
                'releases_last_hour': getattr(allocator, 'release_count_last_hour', 0),
                'reclaims_last_hour': getattr(allocator, 'reclaim_count_last_hour', 0),
            },
            'timestamp': int(time.time()),
        }
    
    def format_html(self, data: Dict[str, Any]) -> str:
        """HTML bar chart display."""
        if 'error' in data:
            return f"<div style='color: red; padding: 10px;'>{data['error']}</div>"
        
        pool = data.get('pool_info', {})
        util = data.get('utilization_percent', 0)
        activity = data.get('recent_activity', {})
        
        # Utilization bar
        util_bar_width = int(util)
        util_bar = '▓' * util_bar_width + '░' * (100 - util_bar_width)
        
        html = f"""
        <div style="padding: 12px; background: #f5f5f5; border-radius: 8px; font-family: monospace;">
            <h3 style="margin: 0 0 10px 0;">🎯 ID Allocation Status</h3>
            
            <div style="background: white; padding: 8px; border-radius: 4px; margin-bottom: 10px; border-left: 4px solid #4CAF50;">
                <div style="font-size: 12px; color: #666;">Pool Utilization</div>
                <div style="margin: 5px 0; font-family: monospace;">{util_bar}</div>
                <div style="font-size: 11px; color: #999;">
                    {pool.get('allocated', 0):,} allocated / {pool.get('total_available', 0):,} total ({util:.1f}%)
                </div>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                <div style="background: white; padding: 8px; border-radius: 4px; border-left: 4px solid #2196F3;">
                    <div style="font-size: 12px; color: #666;">Active IDs</div>
                    <div style="font-size: 18px; font-weight: bold; color: #2196F3;">{pool.get('allocated', 0):,}</div>
                </div>
                <div style="background: white; padding: 8px; border-radius: 4px; border-left: 4px solid #FF9800;">
                    <div style="font-size: 12px; color: #666;">Available</div>
                    <div style="font-size: 18px; font-weight: bold; color: #FF9800;">{pool.get('available', 0):,}</div>
                </div>
                <div style="background: white; padding: 8px; border-radius: 4px; border-left: 4px solid #9C27B0;">
                    <div style="font-size: 12px; color: #666;">Released</div>
                    <div style="font-size: 18px; font-weight: bold; color: #9C27B0;">{pool.get('released', 0):,}</div>
                </div>
                <div style="background: white; padding: 8px; border-radius: 4px; border-left: 4px solid #F44336;">
                    <div style="font-size: 12px; color: #666;">Offline</div>
                    <div style="font-size: 18px; font-weight: bold; color: #F44336;">{pool.get('offline', 0):,}</div>
                </div>
            </div>
            
            <div style="background: white; padding: 8px; border-radius: 4px; margin-top: 10px;">
                <div style="font-size: 12px; color: #666; margin-bottom: 5px;">Last Hour Activity</div>
                <table style="width: 100%; font-size: 12px; border-collapse: collapse;">
                    <tr><td>Allocations:</td><td style="text-align: right;">{activity.get('allocations_last_hour', 0)}</td></tr>
                    <tr><td>Releases:</td><td style="text-align: right;">{activity.get('releases_last_hour', 0)}</td></tr>
                    <tr><td>Reclaims:</td><td style="text-align: right;">{activity.get('reclaims_last_hour', 0)}</td></tr>
                </table>
            </div>
        </div>
        """
        return html
    
    def format_table(self, data: Dict[str, Any]) -> list:
        """Format as table rows."""
        pool = data.get('pool_info', {})
        return [
            {'metric': 'Allocated', 'value': pool.get('allocated', 0)},
            {'metric': 'Available', 'value': pool.get('available', 0)},
            {'metric': 'Released', 'value': pool.get('released', 0)},
            {'metric': 'Offline', 'value': pool.get('offline', 0)},
            {'metric': 'Utilization %', 'value': f"{data.get('utilization_percent', 0):.1f}"},
        ]


def example_auto_load(config=None):
    """
    Example auto_load function showing how to integrate with id_allocator plugin.
    
    In a real id_allocator plugin, this would be:
    
        def auto_load(config=None):
            # ... existing plugin initialization ...
            
            # Register display providers
            register_display_provider(IDLeaseMetricsDisplay())
            register_display_provider(IDAllocationStatusDisplay())
            
            os_log.info('ID_ALLOCATOR', 'AUTO_LOAD', 'Display providers registered', {})
            return True
    """
    register_display_provider(IDLeaseMetricsDisplay())
    register_display_provider(IDAllocationStatusDisplay())
    
    from opensynaptic.utils import os_log
    os_log.info(
        'ID_ALLOCATOR',
        'DISPLAY_PROVIDERS_REGISTERED',
        'ID Allocator display providers registered',
        {'providers': ['lease_metrics', 'allocation_status']}
    )
    
    return True

