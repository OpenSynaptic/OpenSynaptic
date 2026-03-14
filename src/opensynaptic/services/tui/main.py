import json
import time
from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg

_SECTIONS = ('config', 'transport', 'pipeline', 'plugins', 'db', 'identity')

class TUIService:

    def __init__(self, node):
        self.node = node
        self.last_snapshot = {}

    def auto_load(self):
        os_log.log_with_const('info', LogMsg.TUI_READY)
        return self

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

    def run_interactive(self, interval=2.0, sections=None):
        """Blocking loop – clears terminal and reprints every *interval* seconds. Exits on Ctrl+C."""
        os_log.log_with_const('info', LogMsg.TUI_INTERACTIVE, interval=interval)
        print('[TUI Interactive] interval={}s  Ctrl+C 停止'.format(interval), flush=True)
        try:
            while True:
                text = self.render_text(sections)
                print('\033[2J\033[H', end='', flush=True)
                ts = time.strftime('%Y-%m-%d %H:%M:%S')
                print('── OpenSynaptic TUI  [{}]  (Ctrl+C 停止) ──'.format(ts), flush=True)
                print(text, flush=True)
                time.sleep(max(0.5, interval))
        except KeyboardInterrupt:
            print('\n[TUI] 已退出', flush=True)

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

        return {
            'render': _render,
            'interactive': _interactive,
        }
