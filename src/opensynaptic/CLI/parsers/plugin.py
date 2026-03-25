"""Parsers for plugin management and core backend commands.

Commands registered here:
  plugin-list, plugin-load, plugin-cmd, core
"""
import argparse

from .base import add_config_arg
from opensynaptic.CLI.completion import complete_plugin_name, complete_plugin_subcommand


def register(sub: argparse._SubParsersAction) -> None:
    """Attach plugin and core commands to *sub*."""

    # --- plugin-list ---
    plugin_list = sub.add_parser(
        'plugin-list', aliases=['os-plugin-list'],
        help='List mounted service plugins and their running status',
    )
    add_config_arg(plugin_list)

    # --- plugin-load ---
    plugin_load = sub.add_parser(
        'plugin-load', aliases=['os-plugin-load'],
        help='Load a mounted plugin by name',
    )
    add_config_arg(plugin_load)
    plugin_load.add_argument('--name', required=True,
                             help='Plugin name to load (e.g. tui / web_user)')
    plugin_load._actions[-1].completer = complete_plugin_name

    # --- plugin-cmd ---
    plugin_cmd = sub.add_parser(
        'plugin-cmd', aliases=['os-plugin-cmd'],
        help="Route a sub-command to a plugin's CLI handler",
    )
    add_config_arg(plugin_cmd)
    plugin_cmd.add_argument(
        '--plugin', required=True,
        help='Plugin name, e.g. tui / test_plugin / web_user',
    )
    plugin_cmd._actions[-1].completer = complete_plugin_name
    plugin_cmd.add_argument(
        '--cmd', required=True,
        help='Plugin sub-command, e.g. render / interactive / component',
    )
    plugin_cmd._actions[-1].completer = complete_plugin_subcommand
    plugin_cmd.add_argument(
        'args', nargs=argparse.REMAINDER,
        help='Extra arguments passed to the plugin sub-command',
    )

    # --- core ---
    core_cmd = sub.add_parser(
        'core', aliases=['os-core'],
        help='Show current/available cores, optionally switch backend (pycore/rscore)',
    )
    add_config_arg(core_cmd)
    core_cmd.add_argument(
        '--set', dest='set_core',
        choices=['pycore', 'rscore'],
        default=None,
        help='Switch active core in this process (pycore/rscore)',
    )
    core_cmd.add_argument(
        '--persist', action='store_true', default=False,
        help='Persist --set value to Config.json engine_settings.core_backend',
    )
    core_cmd.add_argument(
        '--json', action='store_true', default=False,
        help='Output core status as JSON',
    )

