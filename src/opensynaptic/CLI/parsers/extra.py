"""Parsers for additional utility commands.

Commands registered here:
  status        – quick human-readable node health overview
  id-info       – device identity and ID assignment details
  log-level     – adjust logger verbosity at runtime
  pipeline-info – pipeline configuration summary
  help          – formatted command reference (--full for raw argparse output)
"""
import argparse

from .base import add_config_arg


def register(sub: argparse._SubParsersAction) -> None:
    """Attach utility/extra commands to *sub*."""

    # --- status ---
    status = sub.add_parser(
        'status', aliases=['os-status'],
        help='Quick human-readable node status: ID, transporters, services, core backend',
    )
    add_config_arg(status)
    status.add_argument(
        '--json', action='store_true', default=False,
        help='Output status as machine-readable JSON',
    )

    # --- id-info ---
    id_info = sub.add_parser(
        'id-info', aliases=['os-id-info'],
        help='Show device identity, assigned_id, and ID assignment status',
    )
    add_config_arg(id_info)
    id_info.add_argument(
        '--json', action='store_true', default=False,
        help='Output as JSON',
    )

    # --- log-level ---
    log_level = sub.add_parser(
        'log-level', aliases=['os-log-level'],
        help='Adjust os_log verbosity for the current process at runtime',
    )
    add_config_arg(log_level)
    log_level.add_argument(
        '--set', dest='level',
        choices=['debug', 'info', 'warning', 'error', 'critical'],
        required=True,
        help='New log level (debug/info/warning/error/critical)',
    )

    # --- pipeline-info ---
    pipeline_info = sub.add_parser(
        'pipeline-info', aliases=['os-pipeline-info'],
        help='Show pipeline configuration: stages, precision, zero-copy, cache state',
    )
    add_config_arg(pipeline_info)
    pipeline_info.add_argument(
        '--json', action='store_true', default=False,
        help='Output as JSON',
    )

    # --- help ---
    help_p = sub.add_parser(
        'help', aliases=['os-help'],
        help='Print CLI command reference (add --full for raw argparse output)',
    )
    help_p.add_argument(
        '--full', action='store_true', default=False,
        help='Show full argparse reference instead of the summary table (expert mode)',
    )
