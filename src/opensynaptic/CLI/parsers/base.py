"""Shared argument helpers re-used across multiple CLI parsers.

Import these helpers in each parser module to keep argument definitions DRY.

Example::

    from .base import add_config_arg, add_host_args, add_quiet_arg

    def register(sub):
        p = sub.add_parser('my-cmd')
        add_config_arg(p)
        add_host_args(p)
"""
import argparse


def add_config_arg(parser: argparse.ArgumentParser) -> None:
    """Add ``--config`` / ``dest='config_path'`` to *parser*."""
    parser.add_argument(
        '--config',
        dest='config_path',
        default=None,
        help='Path to Config.json (auto-detected from project root when omitted)',
    )


def add_host_args(parser: argparse.ArgumentParser) -> None:
    """Add ``--host`` and ``--port`` to *parser*."""
    parser.add_argument(
        '--host',
        required=False,
        default=None,
        help='Server hostname or IP address',
    )
    parser.add_argument(
        '--port',
        required=False,
        type=int,
        default=None,
        help='Server port number',
    )


def add_quiet_arg(parser: argparse.ArgumentParser) -> None:
    """Add ``--quiet`` flag to *parser*."""
    parser.add_argument(
        '--quiet',
        action='store_true',
        default=False,
        help='Suppress info logs – only warnings and errors are shown',
    )


def add_run_args(parser: argparse.ArgumentParser) -> None:
    """Add ``--once``, ``--interval``, ``--duration``, and ``--stats-interval`` to *parser*."""
    parser.add_argument(
        '--once',
        action='store_true',
        default=False,
        help='Execute once and exit (no heartbeat loop)',
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=5.0,
        help='Heartbeat polling interval in seconds',
    )
    parser.add_argument(
        '--duration',
        type=float,
        default=0.0,
        help='Total run duration in seconds; 0 = unlimited',
    )
    parser.add_argument(
        '--stats-interval',
        dest='stats_interval',
        type=float,
        default=None,
        help='Periodic run stats interval in seconds (heartbeat logging)',
    )

