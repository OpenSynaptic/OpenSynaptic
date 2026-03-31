"""Assemble the complete os-node argument parser from modular sub-parsers.

Usage::

    from opensynaptic.CLI.build_parser import build_parser

    parser = build_parser()
    args   = parser.parse_args()

Each sub-module in :mod:`opensynaptic.CLI.parsers` exposes a single
``register(sub)`` function that adds its commands to a
:class:`argparse._SubParsersAction`.  This module calls every ``register``
in the canonical order so that ``--help`` output is deterministic.
"""
import argparse
import re
import sys
import difflib

from opensynaptic.CLI.parsers import core, config, test, plugin, native, service, extra
from opensynaptic.CLI.completion import enable_argcomplete


class OSCliArgumentParser(argparse.ArgumentParser):

    def _subparsers_action(self):
        for action in self._actions:
            if isinstance(action, argparse._SubParsersAction):
                return action
        return None

    def _extract_invalid_choice(self, message):
        m = re.search(r"invalid choice:\s*'([^']+)'", str(message or ''))
        return m.group(1) if m else None

    def _candidate_commands(self):
        sub = self._subparsers_action()
        if not sub:
            return []
        # Show canonical command names only in hints.
        return sorted([k for k in sub.choices.keys() if not str(k).startswith('os-')])

    def _service_subcommands(self, command_name):
        sub = self._subparsers_action()
        if not sub:
            return []
        p = sub.choices.get(command_name)
        if p is None:
            return []
        out = []
        for action in getattr(p, '_actions', []):
            choices = getattr(action, 'choices', None)
            if isinstance(choices, (list, tuple, set)):
                for it in choices:
                    s = str(it)
                    if s not in out:
                        out.append(s)
        return out

    def _build_invalid_choice_hints(self, token):
        if not token:
            return []
        cmds = self._candidate_commands()
        if not cmds:
            return []

        token_l = str(token).strip().lower()
        alias_map = {
            'web': 'web-user',
            'webuser': 'web-user',
            'depsmgr': 'deps',
            'dep': 'deps',
            'env': 'env-guard',
            'envguard': 'env-guard',
            'plugin': 'plugin-cmd',
            'plugins': 'plugin-list',
        }

        hints = []
        mapped = alias_map.get(token_l)
        if mapped and mapped in cmds:
            hints.append(f"Did you mean `{mapped}`?")
            subs = self._service_subcommands(mapped)
            if subs:
                preview = ', '.join(subs[:6])
                hints.append(f"`{mapped}` subcommands: {preview}")
                hints.append(f"Example: `os-node {mapped} {subs[0]}`")

        fuzzy = difflib.get_close_matches(token_l, cmds, n=3, cutoff=0.55)
        for cand in fuzzy:
            line = f"Try `{cand}`"
            if line not in hints:
                hints.append(line)

        if not hints:
            hints.append("Use `help` to list commands, or `help --full` for all options.")
        return hints

    def error(self, message):
        msg = str(message or '')
        # Avoid dumping the full command list for minor typos in interactive mode.
        msg = re.sub(r'\(choose from .*\)$', '(use `help` to list commands)', msg)
        sys.stderr.write('os-node: error: {}\n'.format(msg))
        bad = self._extract_invalid_choice(message)
        for hint in self._build_invalid_choice_hints(bad):
            sys.stderr.write('Hint: {}\n'.format(hint))
        sys.stderr.write('Try: help  or  help --full\n')
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    """Build and return the complete ``os-node`` argument parser."""

    parser = OSCliArgumentParser(
        prog='os-node',
        description='OpenSynaptic CLI – 2-N-2 IoT protocol stack control plane',
    )

    # ------------------------------------------------------------------
    # Global / top-level flags (also accepted before any sub-command)
    # ------------------------------------------------------------------
    parser.add_argument(
        '--config', dest='config_path', default=None,
        help='Path to Config.json (auto-detected from project root when omitted)',
    )
    parser.add_argument('--host', required=False, default=None)
    parser.add_argument('--port', required=False, type=int, default=None)
    parser.add_argument('--once', action='store_true', default=False)
    parser.add_argument('--interval', type=float, default=5.0)
    parser.add_argument('--duration', type=float, default=0.0)
    parser.add_argument(
        '--stats-interval', dest='stats_interval', type=float, default=None,
        help='Run-mode periodic stats interval in seconds (main loop heartbeat)',
    )
    parser.add_argument(
        '--quiet', action='store_true', default=False,
        help='Suppress info logs – only warnings and errors are shown',
    )
    parser.add_argument(
        '--yes', action='store_true', default=False,
        help='First-run wizard: auto-accept demo startup prompt',
    )
    parser.add_argument(
        '--no-wizard', action='store_true', default=False,
        help='Skip first-run wizard and continue with normal command flow',
    )

    sub = parser.add_subparsers(dest='command')

    # Register each command group in display order
    core.register(sub)
    config.register(sub)
    test.register(sub)
    plugin.register(sub)
    native.register(sub)
    service.register(sub)
    extra.register(sub)

    enable_argcomplete(parser)

    return parser

