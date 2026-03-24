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
        help='Run web_user plugin directly from CLI',
    )
    add_config_arg(web_user)
    web_user.add_argument(
        '--cmd',
        choices=['start', 'stop', 'status', 'dashboard', 'cli', 'options-schema', 'options-set', 'options-apply', 'list', 'add', 'update', 'delete'],
        default='start',
    )
    web_user.add_argument(
        'args', nargs=argparse.REMAINDER,
        help='Arguments passed to web_user sub-command',
    )

    # --- deps ---
    deps = sub.add_parser(
        'deps', aliases=['os-deps'],
        help='Run dependency_manager plugin directly from CLI',
    )
    add_config_arg(deps)
    deps.add_argument(
        '--cmd',
        choices=['check', 'doctor', 'sync', 'repair', 'install'],
        default='check',
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
    env_guard.add_argument(
        '--cmd',
        choices=['status', 'start', 'stop', 'set', 'resource-show', 'resource-init'],
        default='status',
    )
    env_guard.add_argument(
        'args', nargs=argparse.REMAINDER,
        help='Arguments passed to env_guard sub-command',
    )

