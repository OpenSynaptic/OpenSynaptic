"""
Tests for the refactored Textual-based TUI.

Run with:
    pytest tests/unit/test_textual_tui.py -v
"""

import json
import pytest
from unittest.mock import Mock, patch


class MockNode:
    """Mock OpenSynaptic node for testing."""
    
    def __init__(self):
        self.device_id = "test-device-001"
        self.assigned_id = 12345
        self.config = {
            'VERSION': '1.0.0rc7',
            'engine_settings': {'precision': 4},
            'RESOURCES': {
                'transporters_status': {'udp': True},
                'transport_status': {'udp': True},
            }
        }
        self.active_transporters = {'udp': {}}
        self.standardizer = Mock(registry={})
        self.engine = Mock(REV_UNIT={})
        self.fusion = Mock(_RAM_CACHE={})
        self.db_manager = Mock(dialect='sqlite')
        self.service_manager = Mock()
        self.service_manager.snapshot.return_value = {
            'mount_index': ['web_user'],
            'runtime_index': {'tui': True}
        }


def test_tui_service_import():
    """Test TUIService can be imported."""
    from opensynaptic.services.tui import TUIService
    assert TUIService is not None


def test_tui_render_section():
    """Test TUIService render_section method."""
    from opensynaptic.services.tui import TUIService
    node = MockNode()
    service = TUIService(node)
    
    data = service.render_section('identity')
    assert 'device_id' in data
    assert data['device_id'] == 'test-device-001'


def test_tui_render_text():
    """Test TUIService render_text method."""
    from opensynaptic.services.tui import TUIService
    node = MockNode()
    service = TUIService(node)
    
    text = service.render_text(['identity'])
    data = json.loads(text)
    assert 'identity' in data
    assert 'timestamp' in data


def test_tui_cli_commands():
    """Test TUIService CLI commands."""
    from opensynaptic.services.tui import TUIService
    node = MockNode()
    service = TUIService(node)
    
    commands = service.get_cli_commands()
    assert 'render' in commands
    assert 'interactive' in commands
    assert 'bios' in commands
    assert 'dashboard' in commands


def test_widget_imports():
    """Test all widget modules can be imported."""
    from opensynaptic.services.tui.widgets import (
        BaseTUIPanel,
        IdentityPanel,
        ConfigPanel,
        TransportPanel,
        PipelinePanel,
        PluginsPanel,
        DBPanel,
    )
    assert BaseTUIPanel is not None
    assert IdentityPanel is not None
    assert ConfigPanel is not None

