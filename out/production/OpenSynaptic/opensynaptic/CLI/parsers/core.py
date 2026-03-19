"""Parsers for core operational commands.

Commands registered here:
  run, snapshot, receive, time-sync, ensure-id, transmit,
  inject, decode, watch, tui, reload-protocol,
  transport-status, db-status
"""
import argparse

from .base import add_config_arg, add_host_args, add_quiet_arg, add_run_args


def register(sub: argparse._SubParsersAction) -> None:
    """Attach core commands to *sub*."""

    # --- run ---
    run = sub.add_parser(
        'run', aliases=['os-run'],
        help='Persistent run loop with heartbeat',
    )
    add_config_arg(run)
    add_host_args(run)
    add_quiet_arg(run)
    add_run_args(run)

    # --- snapshot ---
    snapshot = sub.add_parser(
        'snapshot', aliases=['os-snapshot'],
        help='Print node/service/transporter JSON snapshot',
    )
    add_config_arg(snapshot)

    # --- receive ---
    receive = sub.add_parser(
        'receive', aliases=['os-receive'],
        help='Start UDP receiver server',
    )
    add_config_arg(receive)

    # --- tui ---
    tui = sub.add_parser(
        'tui', aliases=['os-tui'],
        help='Render TUI snapshot (add --interactive for live mode)',
    )
    add_config_arg(tui)
    tui.add_argument(
        '--section', default=None,
        help='Render only one section (identity/config/transport/pipeline/plugins/db)',
    )
    tui.add_argument(
        '--interactive', action='store_true', default=False,
        help='Enter interactive BIOS-like mode',
    )
    tui.add_argument(
        '--interval', type=float, default=2.0,
        help='Interactive refresh interval in seconds',
    )

    # --- time-sync ---
    time_sync = sub.add_parser(
        'time-sync', aliases=['os-time-sync'],
        help='Request server timestamp and synchronize',
    )
    add_config_arg(time_sync)

    # --- ensure-id ---
    ensure_id = sub.add_parser(
        'ensure-id', aliases=['os-ensure-id'],
        help='Request device ID from server and persist to Config',
    )
    add_config_arg(ensure_id)
    add_host_args(ensure_id)

    # --- transmit ---
    transmit = sub.add_parser(
        'transmit', aliases=['os-transmit'],
        help='Encode sensor reading(s) and dispatch (single or multi-sensor via --sensors)',
    )
    add_config_arg(transmit)
    transmit.add_argument('--device-id', dest='device_id', default=None)
    transmit.add_argument('--status', default='ONLINE')
    transmit.add_argument('--medium', default='UDP')
    # Single-sensor convenience flags (used when --sensors is not provided)
    transmit.add_argument('--sensor-id', default='V1')
    transmit.add_argument('--sensor-status', default='OK')
    transmit.add_argument('--value', type=float, default=1.0)
    transmit.add_argument('--unit', default='Pa')
    # Multi-sensor flags (override the single-sensor flags when present)
    transmit.add_argument(
        '--sensors', default=None,
        help='JSON array of sensor rows: [["id","status",value,"unit"], ...]',
    )
    transmit.add_argument(
        '--sensors-file', dest='sensors_file', default=None,
        help='Path to a JSON file containing the same array format as --sensors',
    )

    # --- reload-protocol ---
    reload_protocol = sub.add_parser(
        'reload-protocol', aliases=['os-reload-protocol'],
        help='Invalidate and reload one protocol adapter by name',
    )
    add_config_arg(reload_protocol)
    reload_protocol.add_argument('--medium', required=True,
                                 help='Protocol name to reload (e.g. udp, tcp)')

    # --- inject ---
    inject = sub.add_parser(
        'inject', aliases=['os-inject'],
        help='Push data through pipeline stages and inspect output at each stage',
    )
    add_config_arg(inject)
    inject.add_argument(
        '--module',
        choices=['standardize', 'compress', 'fuse', 'full'],
        default='full',
        help='Stop and print after the selected pipeline stage (standardize/compress/fuse/full)',
    )
    inject.add_argument('--device-id', dest='device_id', default=None)
    inject.add_argument('--device-status', dest='device_status', default='ONLINE')
    inject.add_argument('--sensor-id', dest='sensor_id', default='V1')
    inject.add_argument('--sensor-status', dest='sensor_status', default='OK')
    inject.add_argument('--value', type=float, default=1.0)
    inject.add_argument('--unit', default='Pa')
    inject.add_argument(
        '--sensors', default=None,
        help='JSON array for multi-sensor mode: [[id,status,value,unit],...]',
    )
    inject.add_argument(
        '--sensors-file', dest='sensors_file', default=None,
        help='JSON file path (PowerShell-friendly), format: [[id,status,value,unit],...]',
    )

    # --- decode ---
    decode = sub.add_parser(
        'decode', aliases=['os-decode'],
        help='Decode a binary packet (hex) or Base62 string back to JSON',
    )
    add_config_arg(decode)
    decode.add_argument(
        '--format', dest='decode_format', choices=['hex', 'b62'], default='hex',
        help='Input format: hex=binary packet hex string, b62=Base62 compressed string',
    )
    decode.add_argument('--data', required=True, help='Data string to decode')

    # --- watch ---
    watch = sub.add_parser(
        'watch', aliases=['os-watch'],
        help='Real-time poll and print module state changes (Ctrl+C or --duration to stop)',
    )
    add_config_arg(watch)
    watch.add_argument(
        '--module',
        choices=['config', 'registry', 'transport', 'pipeline'],
        default='config',
        help='Module to watch (config/registry/transport/pipeline)',
    )
    watch.add_argument('--interval', type=float, default=2.0,
                       help='Polling interval in seconds')
    watch.add_argument('--duration', type=float, default=0.0,
                       help='Total duration in seconds; 0 = unlimited')

    # --- transport-status ---
    transport_status = sub.add_parser(
        'transport-status', aliases=['os-transport-status'],
        help='Show all transporter layer states',
    )
    add_config_arg(transport_status)

    # --- db-status ---
    db_status = sub.add_parser(
        'db-status', aliases=['os-db-status'],
        help='Show DB engine enabled state and dialect',
    )
    add_config_arg(db_status)

