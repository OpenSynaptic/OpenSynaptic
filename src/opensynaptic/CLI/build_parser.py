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

from opensynaptic.CLI.parsers import core, config, test, plugin, native, service, extra


def build_parser() -> argparse.ArgumentParser:
    """Build and return the complete ``os-node`` argument parser."""

    parser = argparse.ArgumentParser(
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
        '--quiet', action='store_true', default=False,
        help='Suppress info logs – only warnings and errors are shown',
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

    return parser

