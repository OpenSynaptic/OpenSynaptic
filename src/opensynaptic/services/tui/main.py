import json
import time
from opensynaptic.utils import (
    os_log,
    LogMsg,
)

_SECTIONS = ('config', 'transport', 'pipeline', 'plugins', 'db', 'identity')

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

    # ------------------------------------------------------------------ #
    #  Individual section renderers                                        #
    # ------------------------------------------------------------------ #

    def _section_identity(self):
        return {
            'device_id': getattr(self.node, 'device_id', 'UNKNOWN'),
            'assigned_id': getattr(self.node, 'assigned_id', None),
            'version': getattr(self.node, 'config', {}).get('VERSION', '?'),
        }

    def _section_config(self):
        cfg = getattr(self.node, 'config', {})
        return {
            'engine_settings': cfg.get('engine_settings', {}),
            'payload_switches': cfg.get('payload_switches', {}),
            'OpenSynaptic_Setting': cfg.get('OpenSynaptic_Setting', {}),
            'security_settings': cfg.get('security_settings', {}),
        }

    def _section_transport(self):
        cfg = getattr(self.node, 'config', {})
        res = cfg.get('RESOURCES', {})
        return {
            'active_transporters': sorted(list(getattr(self.node, 'active_transporters', {}).keys())),
            'transporters_status': res.get('transporters_status', {}),
            'transport_status': res.get('transport_status', {}),
            'physical_status': res.get('physical_status', {}),
            'application_status': res.get('application_status', {}),
        }

    def _section_pipeline(self):
        n = self.node
        return {
            'standardizer_cache_entries': len(getattr(getattr(n, 'standardizer', None), 'registry', {})),
            'engine_rev_unit_entries': len(getattr(getattr(n, 'engine', None), 'REV_UNIT', {})),
            'fusion_ram_cache_aids': list(getattr(getattr(n, 'fusion', None), '_RAM_CACHE', {}).keys()),
            'fusion_template_count': sum(
                len(v.get('data', {}).get('templates', {}))
                for v in getattr(getattr(n, 'fusion', None), '_RAM_CACHE', {}).values()
            ),
        }

    def _section_plugins(self):
        if hasattr(self.node, 'service_manager'):
            snap = self.node.service_manager.snapshot()
            return {'mount_index': snap.get('mount_index', []), 'runtime_index': snap.get('runtime_index', {})}
        return {}

    def _section_db(self):
        db = getattr(self.node, 'db_manager', None)
        return {
            'enabled': bool(db),
            'dialect': getattr(db, 'dialect', None),
        }

    _SECTION_METHODS = {
        'identity': '_section_identity',
        'config': '_section_config',
        'transport': '_section_transport',
        'pipeline': '_section_pipeline',
        'plugins': '_section_plugins',
        'db': '_section_db',
    }

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def render_section(self, name):
        """Return a dict for a single named section."""
        method_name = self._SECTION_METHODS.get(str(name).lower())
        if method_name is None:
            return {'error': 'Unknown section "{}". Available: {}'.format(name, sorted(self._SECTION_METHODS.keys()))}
        result = getattr(self, method_name)()
        os_log.log_with_const('info', LogMsg.TUI_SECTION, section=name)
        return result

    def render_sections(self, sections=None):
        """Return a dict keyed by section name. Pass None for all sections."""
        names = sections if sections else list(self._SECTION_METHODS.keys())
        return {n: self.render_section(n) for n in names}

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
        rows = [
            '+' + ('-' * 78) + '+',
            '| OpenSynaptic BIOS Console'.ljust(79) + '|',
            '| Time: {} | Active: {} | Refresh: {:.2f}s | Last render: {:.3f}s'.format(ts, active_section, interval, elapsed_s).ljust(79) + '|',
            '+' + ('-' * 78) + '+',
            '| Sections:'.ljust(79) + '|',
        ]
        for idx, name in enumerate(_SECTIONS, start=1):
            marker = '*' if name == active_section else ' '
            rows.append('|  {} {}. {}'.format(marker, idx, name).ljust(79) + '|')
        rows.extend([
            '+' + ('-' * 78) + '+',
            '| Commands:'.ljust(79) + '|',
            '|   [1-6] switch section   [a] all sections   [r] refresh current'.ljust(79) + '|',
            '|   [auto N] auto-refresh N cycles            [i SEC] set interval'.ljust(79) + '|',
            '|   [j] print JSON payload                     [h/?] help'.ljust(79) + '|',
            '|   [p] plugin snapshot                        [q] quit'.ljust(79) + '|',
            '+' + ('-' * 78) + '+',
        ])
        self._clear_screen()
        print('\n'.join(rows), flush=True)
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str), flush=True)

    def run_bios(self, interval=2.0, section=None):
        """Interactive BIOS-like terminal shell for exploring service state."""
        os_log.log_with_const('info', LogMsg.TUI_INTERACTIVE, interval=interval)
        current = (section or 'identity').lower()
        if current not in self._SECTION_METHODS:
            current = 'identity'
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
            if cmd in ('h', '?', 'help'):
                print('Commands: 1-6 | a | r | auto N | i SEC | j | p | q', flush=True)
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
                if 0 <= idx < len(_SECTIONS):
                    current = _SECTIONS[idx]
                continue
            if cmd in self._SECTION_METHODS:
                current = cmd
                continue

    def run_interactive(self, interval=2.0, sections=None):
        """Backward-compatible interactive entrypoint; now routes to BIOS mode."""
        selected = sections[0] if sections else None
        return self.run_bios(interval=interval, section=selected)

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
            ns = p.parse_args(argv)
            sections = [ns.section] if ns.section else None
            self.run_interactive(interval=ns.interval, sections=sections)
            return 0

        def _bios(argv):
            import argparse
            p = argparse.ArgumentParser(prog='tui bios')
            p.add_argument('--interval', type=float, default=2.0)
            p.add_argument('--section', default=None)
            ns = p.parse_args(argv)
            self.run_bios(interval=ns.interval, section=ns.section)
            return 0

        return {
            'render': _render,
            'interactive': _interactive,
            'bios': _bios,
        }
