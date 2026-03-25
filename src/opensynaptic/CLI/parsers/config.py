"""Parsers for configuration commands.

Commands registered here:
  config-show, config-get, config-set, transporter-toggle
"""
import argparse

from .base import add_config_arg
from opensynaptic.CLI.completion import complete_config_path, complete_transporter


def register(sub: argparse._SubParsersAction) -> None:
    """Attach config commands to *sub*."""

    # --- config-show ---
    config_show = sub.add_parser(
        'config-show', aliases=['os-config-show'],
        help='Display Config.json or a specific section',
    )
    add_config_arg(config_show)
    config_show.add_argument(
        '--section', default=None,
        help='Top-level section name; leave empty to print all',
    )

    # --- config-get ---
    config_get = sub.add_parser(
        'config-get', aliases=['os-config-get'],
        help='Read a dot-notation key path from Config.json',
    )
    add_config_arg(config_get)
    config_get.add_argument(
        '--key', required=True,
        help='Dot path, for example: engine_settings.precision',
    )
    config_get._actions[-1].completer = complete_config_path

    # --- config-set ---
    config_set = sub.add_parser(
        'config-set', aliases=['os-config-set'],
        help='Write a typed value to a dot-notation key path in Config.json',
    )
    add_config_arg(config_set)
    config_set.add_argument(
        '--key', required=True,
        help='Dot path, for example: engine_settings.precision',
    )
    config_set._actions[-1].completer = complete_config_path
    config_set.add_argument(
        '--value', required=True,
        help='New value string (use --type for conversion)',
    )
    config_set.add_argument(
        '--type', dest='value_type',
        choices=['str', 'int', 'float', 'bool', 'json'],
        default='str',
        help='Value type (str/int/float/bool/json), default=str',
    )

    # --- transporter-toggle ---
    transporter_toggle = sub.add_parser(
        'transporter-toggle', aliases=['os-transporter-toggle'],
        help='Enable or disable a transporter in Config.json',
    )
    add_config_arg(transporter_toggle)
    transporter_toggle.add_argument(
        '--name', required=True,
        help='Transporter name (lowercase), e.g. udp / tcp / lora',
    )
    transporter_toggle._actions[-1].completer = complete_transporter
    tog_group = transporter_toggle.add_mutually_exclusive_group(required=True)
    tog_group.add_argument('--enable', action='store_true', default=False)
    tog_group.add_argument('--disable', action='store_true', default=False)

