"""Parsers for standalone service plugin commands.

Commands registered here:
  web-user, deps, env-guard
"""
import argparse

from .base import add_config_arg


def register(sub: argparse._SubParsersAction) -> None:
    """Attach service plugin commands to *sub*."""

    # --- web-user ---
    web_user = sub.add_parser(
        'web-user', aliases=['os-web-user', 'os-web'],
        help='Control web_user service (start, stop, status, etc.)',
    )
    add_config_arg(web_user)
    
    # Support both --cmd and positional subcommand for better UX
    # Priority: positional subcommand > --cmd > default 'start'
    web_user.add_argument(
        'subcommand',
        nargs='?',
        default=None,
        choices=['start', 'stop', 'status', 'dashboard', 'cli', 'options-schema', 
                 'options-set', 'options-apply', 'list', 'add', 'update', 'delete'],
        help='Subcommand to execute (start, stop, status, etc.)',
    )
    web_user.add_argument(
        '--cmd',
        dest='cmd_flag',
        choices=['start', 'stop', 'status', 'dashboard', 'cli', 'options-schema', 
                'options-set', 'options-apply', 'list', 'add', 'update', 'delete'],
        default=None,
        help='Alternative way to specify subcommand (legacy support)',
    )
    web_user.add_argument(
        'args', nargs=argparse.REMAINDER,
        help='Arguments passed to sub-command',
    )

    # --- deps ---
    deps = sub.add_parser(
        'deps', aliases=['os-deps'],
        help='Dependency manager (check, doctor, sync, repair, install)',
    )
    add_config_arg(deps)
    
    # Support both --cmd and positional subcommand
    deps.add_argument(
        'subcommand',
        nargs='?',
        default=None,
        choices=['check', 'doctor', 'sync', 'repair', 'install'],
        help='Subcommand to execute',
    )
    deps.add_argument(
        '--cmd',
        dest='cmd_flag',
        choices=['check', 'doctor', 'sync', 'repair', 'install'],
        default=None,
        help='Alternative way to specify subcommand (legacy support)',
    )
    deps.add_argument(
        'args', nargs=argparse.REMAINDER,
        help='Arguments passed to dependency_manager sub-command',
    )

    # --- env-guard ---
    env_guard = sub.add_parser(
        'env-guard', aliases=['os-env-guard'],
        help='Environment guard plugin (error monitor + resource/status management)',
    )
    add_config_arg(env_guard)
    
    # Support both --cmd and positional subcommand
    env_guard.add_argument(
        'subcommand',
        nargs='?',
        default=None,
        choices=['status', 'start', 'stop', 'set', 'resource-show', 'resource-init'],
        help='Subcommand to execute',
    )
    env_guard.add_argument(
        '--cmd',
        dest='cmd_flag',
        choices=['status', 'start', 'stop', 'set', 'resource-show', 'resource-init'],
        default=None,
        help='Alternative way to specify subcommand (legacy support)',
    )
    env_guard.add_argument(
        'args', nargs=argparse.REMAINDER,
        help='Arguments passed to env_guard sub-command',
    )



