"""Parsers for additional utility commands.

Commands registered here:
  status        – quick human-readable node health overview
  id-info       – device identity and ID assignment details
  log-level     – adjust logger verbosity at runtime
  pipeline-info – pipeline configuration summary
  wizard/init   – interactive config generator
  repair-config – repair/bootstrap user config for local demo workflows
  doctor/diagnose – run system diagnostics and optional self-heal
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

    # --- repair-config ---
    repair_cfg = sub.add_parser(
        'repair-config', aliases=['os-repair-config'],
        help='Repair or initialize user config (~/.config/opensynaptic/Config.json) for local loopback use',
    )
    add_config_arg(repair_cfg)
    repair_cfg.add_argument(
        '--json', action='store_true', default=False,
        help='Output result as JSON',
    )

    # --- doctor / diagnose ---
    doctor = sub.add_parser(
        'doctor', aliases=['diagnose', 'os-doctor', 'os-diagnose'],
        help='Run environment/config/transporter diagnostics and print repair suggestions',
    )
    add_config_arg(doctor)
    doctor.add_argument(
        '--json', action='store_true', default=False,
        help='Output diagnosis report as JSON',
    )
    doctor.add_argument(
        '--self-heal', action='store_true', default=False,
        help='Auto-backup corrupted config and fill required missing keys',
    )

    # --- wizard / init ---
    wizard = sub.add_parser(
        'wizard', aliases=['init', 'os-wizard', 'os-init'],
        help='Interactive configuration wizard (or --default for non-interactive setup)',
    )
    add_config_arg(wizard)
    wizard.add_argument(
        '--default', action='store_true', default=False,
        help='Generate default localhost config and skip questions',
    )

    # --- restart ---
    restart = sub.add_parser(
        'restart', aliases=['os-restart'],
        help='Gracefully restart the run loop: stop current receiver, start new run process',
    )
    add_config_arg(restart)
    restart.add_argument(
        '--graceful', action='store_true', default=True,
        help='Enable graceful shutdown (waits for pending operations; default: enabled)',
    )
    restart.add_argument(
        '--timeout', type=float, default=10.0,
        help='Timeout in seconds to wait for graceful shutdown (default: 10.0)',
    )
    restart.add_argument(
        '--host', type=str, default=None,
        help='Server host for ID assignment (optional, uses config if not specified)',
    )
    restart.add_argument(
        '--port', type=int, default=None,
        help='Server port for ID assignment (optional, uses config if not specified)',
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
