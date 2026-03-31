import json
import time
from opensynaptic.utils import (
    os_log,
    LogMsg,
)
from opensynaptic.services.display_api import (
    get_display_registry,
    render_section,
    DisplayFormat,
)

_SECTIONS = ('identity', 'config', 'transport', 'pipeline', 'plugins', 'db')


class TUIService:

    def __init__(self, node):
        self.node = node
        self.last_snapshot = {}

    def auto_load(self):
        os_log.log_with_const('info', LogMsg.TUI_READY)
        return self

    @staticmethod
    def get_required_config():
        return {
            'enabled': True,
            'mode': 'manual',
            'default_section': 'identity',
            'default_interval': 2.0,
        }

    # Note: All _section_* methods have been moved to builtin_display_providers.py
    # as Display Providers:
    # - IdentityDisplayProvider
    # - ConfigDisplayProvider  
    # - TransportDisplayProvider
    # - PipelineDisplayProvider
    # - PluginsDisplayProvider
    # - DatabaseDisplayProvider
    #
    # This is now handled by render_section() via Display API below.

    # ------------------------------------------------------------------ #
    #  Public API (Simplified via Display Providers)                     #
    # ------------------------------------------------------------------ #

    def render_section(self, name):
        """Return a dict for a single named section via Display API.
        
        All sections are now provided by Display Providers, either builtin
        (opensynaptic_core:*) or from plugins.
        """
        name_lower = str(name).lower()
        
        # Try builtin sections first (from builtin_display_providers)
        if name_lower in _SECTIONS:
            output = render_section('opensynaptic_core', name_lower, DisplayFormat.JSON, node=self.node)
            if output is not None:
                os_log.log_with_const('info', LogMsg.TUI_SECTION, section=name)
                return output
        
        # Try as plugin:section format
        if ':' in name:
            plugin_name, section_id = name.split(':', 1)
            output = render_section(plugin_name, section_id, DisplayFormat.JSON, node=self.node)
            if output is not None:
                os_log.log_with_const('info', LogMsg.TUI_SECTION, section=name)
                return output
        
        # Not found
        available = self.get_available_sections()
        providers = []
        for item in (available.get('providers_list') or []):
            key = item[0] if isinstance(item, (tuple, list)) and item else item
            if not key:
                continue
            parts = str(key).split(':', 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                providers.append(f"{parts[0]}:{parts[1]}")
        return {
            'error': f'Unknown section "{name}"',
            'available_builtin': available['builtin'],
            'available_providers': providers,
        }

    def render_sections(self, sections=None):
        """Return a dict keyed by section name. Pass None for all sections."""
        if sections is None:
            available = self.get_available_sections()
            builtin = list(available.get('builtin') or [])
            providers = []
            for item in (available.get('providers_list') or []):
                key = item[0] if isinstance(item, (tuple, list)) and item else item
                if not key:
                    continue
                parts = str(key).split(':', 1)
                if len(parts) == 2 and parts[0] and parts[1]:
                    providers.append(f"{parts[0]}:{parts[1]}")
            sections = builtin + providers
        
        return {n: self.render_section(n) for n in sections}

    def get_available_sections(self) -> dict:
        """Get metadata about all available sections (builtin + providers)."""
        registry = get_display_registry()
        
        return {
            'builtin': _SECTIONS,
            'providers_list': registry.list_all(),
            'providers_metadata': registry.get_metadata(),
        }

    def build_snapshot(self):
        snapshot = self.render_sections()
        snapshot['timestamp'] = int(time.time())
        self.last_snapshot = snapshot
        return snapshot

    def render_text(self, sections=None):
        data = self.render_sections(sections)
        data['timestamp'] = int(time.time())
        self.last_snapshot = data
        os_log.log_with_const('info', LogMsg.TUI_RENDER, section=str(sections or 'all'))
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)

    def run_once(self, sections=None):
        return self.render_text(sections)

    @staticmethod
    def _clear_screen():
        print('\033[2J\033[H', end='', flush=True)

    def _render_bios_screen(self, active_section, interval, payload, elapsed_s):
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        
        # Build dynamic section list from built-in + providers
        builtin_sections = list(_SECTIONS)
        registry = get_display_registry()
        provider_sections = [f"{pname}:{sid}" for pname, sid in [
            k.split(':', 1) for k in [key for key, _ in registry.list_all()]
        ]]
        all_sections = builtin_sections + provider_sections
        
        rows = [
            '+' + ('-' * 78) + '+',
            '| OpenSynaptic BIOS Console (with Display API Providers)'.ljust(79) + '|',
            '| Time: {} | Active: {} | Refresh: {:.2f}s | Last render: {:.3f}s'.format(ts, active_section, interval, elapsed_s).ljust(79) + '|',
            '+' + ('-' * 78) + '+',
            '| Built-in Sections:'.ljust(79) + '|',
        ]
        for idx, name in enumerate(builtin_sections, start=1):
            marker = '*' if name == active_section else ' '
            rows.append('|  {} {}. {}'.format(marker, idx, name).ljust(79) + '|')
        
        if provider_sections:
            rows.append('| Display API Providers:'.ljust(79) + '|')
            for idx, name in enumerate(provider_sections, start=len(builtin_sections) + 1):
                marker = '*' if name == active_section else ' '
                rows.append('|  {} {}. {}'.format(marker, idx, name).ljust(79) + '|')
        
        rows.extend([
            '+' + ('-' * 78) + '+',
            '| Commands:'.ljust(79) + '|',
            '|   [1-N] switch section     [a] all sections   [r] refresh current'.ljust(79) + '|',
            '|   [auto N] auto-refresh    [i SEC] set interval  [m] list metadata'.ljust(79) + '|',
            '|   [j] print JSON payload   [h/?] help         [p] plugins'.ljust(79) + '|',
            '|   [q] quit                                        [s] search'.ljust(79) + '|',
            '+' + ('-' * 78) + '+',
        ])
        self._clear_screen()
        print('\n'.join(rows), flush=True)
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str), flush=True)

    def run_bios(self, interval=2.0, section=None):
        """Interactive BIOS-like terminal shell for exploring service state."""
        os_log.log_with_const('info', LogMsg.TUI_INTERACTIVE, interval=interval)
        
        # Build dynamic section list
        builtin_sections = list(_SECTIONS)
        registry = get_display_registry()
        provider_sections = [f"{pname}:{sid}" for pname, sid in [
            k.split(':', 1) for k in [key for key, _ in registry.list_all()]
        ]]
        all_sections = builtin_sections + provider_sections
        
        current = (section or 'identity').lower()
        if current not in all_sections:
            current = builtin_sections[0] if builtin_sections else 'identity'
        interval = max(0.2, float(interval))
        
        while True:
            t0 = time.monotonic()
            payload = self.render_section(current)
            elapsed_s = time.monotonic() - t0
            self._render_bios_screen(current, interval, payload, elapsed_s)
            try:
                command = input('bios> ').strip()
            except (EOFError, KeyboardInterrupt):
                print('\n[TUI] Exited.', flush=True)
                return
            if not command:
                continue
            cmd = command.lower()
            if cmd in ('q', 'quit', 'exit'):
                print('[TUI] Exited.', flush=True)
                return
            if cmd in ('a', 'all'):
                self._clear_screen()
                print(self.render_text(), flush=True)
                input('Press Enter to return to BIOS view...')
                continue
            if cmd in ('j', 'json'):
                print(json.dumps(payload, indent=2, ensure_ascii=False, default=str), flush=True)
                input('Press Enter to return to BIOS view...')
                continue
            if cmd in ('m', 'metadata'):
                print(json.dumps(self.get_available_sections(), indent=2, ensure_ascii=False), flush=True)
                input('Press Enter to return to BIOS view...')
                continue
            if cmd in ('h', '?', 'help'):
                print('Commands: 1-N | a | r | auto N | i SEC | j | m | p | s | q', flush=True)
                print('  1-N: switch section  a: all sections  r: refresh current  auto N: auto-refresh')
                print('  i SEC: set interval  j: JSON payload  m: metadata  p: plugins  s: search  q: quit')
                input('Press Enter to return to BIOS view...')
                continue
            if cmd in ('s', 'search'):
                query = input('Search sections (partial name): ').strip().lower()
                matching = [sec for sec in all_sections if query in sec.lower()]
                if matching:
                    print(json.dumps({'matching': matching}, indent=2), flush=True)
                else:
                    print('No matching sections found.')
                input('Press Enter to return to BIOS view...')
                continue
            if cmd in ('p', 'plugin'):
                plugins = {}
                if hasattr(self.node, 'service_manager'):
                    plugins = self.node.service_manager.collect_cli_commands()
                print(json.dumps({'plugins': sorted(list(plugins.keys()))}, indent=2, ensure_ascii=False), flush=True)
                input('Press Enter to return to BIOS view...')
                continue
            if cmd in ('r', 'refresh'):
                continue
            if cmd.startswith('i '):
                try:
                    interval = max(0.2, float(cmd.split(None, 1)[1]))
                except Exception:
                    pass
                continue
            if cmd.startswith('auto '):
                try:
                    cycles = max(1, int(cmd.split(None, 1)[1]))
                except Exception:
                    cycles = 5
                for _ in range(cycles):
                    t0 = time.monotonic()
                    payload = self.render_section(current)
                    elapsed_s = time.monotonic() - t0
                    self._render_bios_screen(current, interval, payload, elapsed_s)
                    time.sleep(interval)
                continue
            if cmd.isdigit():
                idx = int(cmd) - 1
                if 0 <= idx < len(all_sections):
                    current = all_sections[idx]
                continue
            if cmd in all_sections:
                current = cmd
                continue

    def run_interactive(self, interval=2.0, sections=None):
        """Backward-compatible interactive entrypoint; now routes to Textual mode."""
        selected = sections[0] if sections else None
        return self.run_textual(interval=interval, section=selected)

    def run_textual(self, interval=2.0, section=None, mode: str = 'interactive'):
        """Run the modern Textual-based TUI.
        
        Args:
            interval: Refresh interval in seconds
            section: Initial section to display
            mode: 'interactive' (full UI) or 'once' (snapshot)
        """
        try:
            from .textual_app import TextualTUIApp
            
            app = TextualTUIApp(self, interval=interval, section=section)
            if mode == 'once':
                return app.run_once()
            else:
                app.run()
        except ImportError:
            # Graceful fallback to BIOS mode if Textual not installed
            os_log.info(
                'TUI',
                'TEXTUAL_FALLBACK',
                'Textual not available; falling back to BIOS mode',
                {}
            )
            return self.run_bios(interval=interval, section=section)

    # ------------------------------------------------------------------ #
    #  Plugin CLI integration                                              #
    # ------------------------------------------------------------------ #

    def get_cli_commands(self):
        """Expose TUI sub-commands to ServiceManager.dispatch_plugin_cli()."""
        def _render(argv):
            import argparse
            p = argparse.ArgumentParser(prog='tui render')
            p.add_argument('--section', default=None)
            ns = p.parse_args(argv)
            sections = [ns.section] if ns.section else None
            print(self.render_text(sections))
            return 0

        def _interactive(argv):
            import argparse
            p = argparse.ArgumentParser(prog='tui interactive')
            p.add_argument('--interval', type=float, default=2.0)
            p.add_argument('--section', default=None)
            p.add_argument('--mode', choices=['textual', 'bios'], default='textual',
                           help='UI mode: textual (default) or bios (fallback)')
            ns = p.parse_args(argv)
            sections = [ns.section] if ns.section else None
            
            if ns.mode == 'bios':
                self.run_bios(interval=ns.interval, section=ns.section)
            else:
                self.run_textual(interval=ns.interval, section=ns.section, mode='interactive')
            return 0

        def _bios(argv):
            import argparse
            p = argparse.ArgumentParser(prog='tui bios')
            p.add_argument('--interval', type=float, default=2.0)
            p.add_argument('--section', default=None)
            ns = p.parse_args(argv)
            self.run_bios(interval=ns.interval, section=ns.section)
            return 0

        def _dashboard(argv):
            """Textual-only dashboard mode."""
            import argparse
            p = argparse.ArgumentParser(prog='tui dashboard')
            p.add_argument('--interval', type=float, default=2.0)
            p.add_argument('--section', default=None)
            ns = p.parse_args(argv)
            self.run_textual(interval=ns.interval, section=ns.section, mode='interactive')
            return 0

        return {
            'render': _render,
            'interactive': _interactive,
            'bios': _bios,
            'dashboard': _dashboard,
        }
