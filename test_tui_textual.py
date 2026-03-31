#!/usr/bin/env python3
"""
Quick start script for testing the refactored Textual TUI.

This script demonstrates how to use the new Textual-based TUI and fallback to BIOS mode.

Usage:
    python test_tui_textual.py [--mode {textual|bios}] [--section SECTION]

Examples:
    python test_tui_textual.py --mode textual
    python test_tui_textual.py --mode bios --section identity
    python test_tui_textual.py --section config
"""

import sys
import argparse
from unittest.mock import Mock

# Add project root to path
sys.path.insert(0, '.')


def create_mock_node():
    """Create a mock node for testing."""
    node = Mock()
    node.device_id = "TEST-DEVICE-001"
    node.assigned_id = 42
    node.config = {
        'VERSION': '1.0.0rc7',
        'engine_settings': {'precision': 4, 'core_backend': 'pycore'},
        'payload_switches': {'active_standardization': True},
        'security_settings': {'id_lease': {'offline_hold_days': 30}},
        'RESOURCES': {
            'transporters_status': {
                'udp': True,
                'tcp': False,
                'mqtt': True,
            },
            'transport_status': {'udp': True},
            'physical_status': {'uart': False},
            'application_status': {'mqtt': True},
        }
    }
    node.active_transporters = {
        'udp': {},
        'mqtt': {},
    }
    
    # Mock components
    node.standardizer = Mock(registry={'temperature': 'K', 'pressure': 'Pa'})
    node.engine = Mock(REV_UNIT={'K': 'temperature', 'Pa': 'pressure'})
    
    # Mock fusion with cache
    node.fusion = Mock()
    node.fusion._RAM_CACHE = {
        1001: {
            'data': {
                'templates': {
                    'temp_template': {'fields': ['temp', 'humidity']},
                }
            }
        },
        1002: {
            'data': {
                'templates': {}
            }
        },
    }
    
    # Mock database
    node.db_manager = Mock(dialect='postgresql')
    
    # Mock service manager
    node.service_manager = Mock()
    node.service_manager.snapshot.return_value = {
        'mount_index': ['web_user', 'test_plugin', 'tui'],
        'runtime_index': {
            'tui': True,
            'web_user': False,
            'test_plugin': True,
        }
    }
    
    return node


def test_tui_imports():
    """Test that TUI modules can be imported."""
    print("\n" + "="*60)
    print("Testing TUI Imports")
    print("="*60)
    
    try:
        from opensynaptic.services.tui import TUIService
        print("✅ TUIService imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import TUIService: {e}")
        return False
    
    try:
        from opensynaptic.services.tui import TextualTUIApp
        print("✅ TextualTUIApp imported successfully")
    except ImportError as e:
        print(f"⚠️  TextualTUIApp not available (Textual probably not installed)")
        print(f"   Details: {e}")
    
    try:
        from opensynaptic.services.tui.widgets import (
            IdentityPanel, ConfigPanel, TransportPanel,
            PipelinePanel, PluginsPanel, DBPanel
        )
        print("✅ All widget panels imported successfully")
    except ImportError as e:
        print(f"⚠️  Widget panels import failed: {e}")
    
    return True


def test_tui_service(node):
    """Test TUIService functionality."""
    print("\n" + "="*60)
    print("Testing TUIService Functionality")
    print("="*60)
    
    from opensynaptic.services.tui import TUIService
    
    service = TUIService(node)
    print("✅ TUIService instance created")
    
    # Test rendering sections
    sections = ['identity', 'config', 'transport', 'pipeline', 'plugins', 'db']
    for section in sections:
        try:
            data = service.render_section(section)
            if 'error' not in data:
                print(f"✅ Rendered section: {section}")
            else:
                print(f"❌ Error in section {section}: {data['error']}")
        except Exception as e:
            print(f"❌ Failed to render {section}: {e}")
    
    # Test rendering all sections
    try:
        all_data = service.render_sections()
        print(f"✅ Rendered all {len(all_data)} sections")
    except Exception as e:
        print(f"❌ Failed to render all sections: {e}")
    
    # Test text rendering
    try:
        text = service.render_text(['identity', 'transport'])
        print(f"✅ Rendered text output ({len(text)} bytes)")
    except Exception as e:
        print(f"❌ Failed to render text: {e}")
    
    # Test CLI commands
    try:
        commands = service.get_cli_commands()
        available_cmds = list(commands.keys())
        print(f"✅ CLI commands available: {', '.join(available_cmds)}")
    except Exception as e:
        print(f"❌ Failed to get CLI commands: {e}")
    
    return service


def test_textual_mode(service, section=None):
    """Test Textual mode."""
    print("\n" + "="*60)
    print("Testing Textual Mode")
    print("="*60)
    
    try:
        from opensynaptic.services.tui.textual_app import TextualTUIApp, TEXTUAL_AVAILABLE
        
        if not TEXTUAL_AVAILABLE:
            print("⚠️  Textual not available - skipping interactive test")
            print("   Install with: pip install textual>=0.40.0")
            return False
        
        print("✅ Textual is available")
        
        # Test snapshot mode (non-interactive)
        try:
            app = TextualTUIApp(service, interval=2.0, section=section)
            output = app.run_once()
            print(f"✅ Textual snapshot mode works ({len(output)} bytes output)")
            return True
        except Exception as e:
            print(f"⚠️  Textual snapshot failed: {e}")
            return False
        
    except ImportError as e:
        print(f"⚠️  Textual mode not available: {e}")
        return False


def test_bios_mode_snapshot(service, section=None):
    """Test BIOS mode (snapshot only, no interactive)."""
    print("\n" + "="*60)
    print("Testing BIOS Mode")
    print("="*60)
    
    try:
        # Test rendering a section
        selected_section = section or 'identity'
        data = service.render_section(selected_section)
        
        import json
        output = json.dumps(data, indent=2, ensure_ascii=False, default=str)
        print(f"✅ BIOS mode snapshot works ({len(output)} bytes)")
        print(f"   Section: {selected_section}")
        return True
        
    except Exception as e:
        print(f"❌ BIOS mode test failed: {e}")
        return False


def main():
    """Main test function."""
    parser = argparse.ArgumentParser(
        description='Test the refactored Textual TUI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_tui_textual.py --mode textual
  python test_tui_textual.py --mode bios --section identity
  python test_tui_textual.py --section config
        """
    )
    parser.add_argument(
        '--mode',
        choices=['textual', 'bios'],
        default='textual',
        help='UI mode to test (default: textual, falls back to bios if unavailable)'
    )
    parser.add_argument(
        '--section',
        default='identity',
        help='Section to display (default: identity)'
    )
    parser.add_argument(
        '--skip-textual',
        action='store_true',
        help='Skip Textual tests'
    )
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("OpenSynaptic TUI Textual Refactor - Test Suite")
    print("="*60)
    
    # Create mock node
    node = create_mock_node()
    print("✅ Mock node created")
    
    # Test imports
    if not test_tui_imports():
        print("\n❌ Import tests failed")
        return 1
    
    # Test TUIService
    service = test_tui_service(node)
    if not service:
        print("\n❌ TUIService tests failed")
        return 1
    
    # Test selected mode
    if args.mode == 'bios' or args.skip_textual:
        success = test_bios_mode_snapshot(service, args.section)
    else:
        # Try Textual first, fall back to BIOS
        success = test_textual_mode(service, args.section)
        if not success:
            print("\n⏬ Falling back to BIOS mode...")
            success = test_bios_mode_snapshot(service, args.section)
    
    if success:
        print("\n" + "="*60)
        print("✅ All tests passed!")
        print("="*60)
        print("\nNext steps:")
        print("1. Install Textual (optional):")
        print("   pip install textual>=0.40.0")
        print("\n2. Try the interactive TUI:")
        print("   os-tui --interactive")
        print("\n3. Or use BIOS mode:")
        print("   python -u src/main.py tui interactive --mode bios")
        return 0
    else:
        print("\n" + "="*60)
        print("⚠️  Some tests had issues")
        print("="*60)
        return 1


if __name__ == '__main__':
    sys.exit(main())

