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

from opensynaptic.CLI.parsers import core, config, test, plugin, native, service, extra
from opensynaptic.CLI.completion import enable_argcomplete


class OSCliArgumentParser(argparse.ArgumentParser):

    def error(self, message):
        msg = str(message or '')
        # Avoid dumping the full command list for minor typos in interactive mode.
        msg = re.sub(r'\(choose from .*\)$', '(use `help` to list commands)', msg)
        sys.stderr.write('os-node: error: {}\n'.format(msg))
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

