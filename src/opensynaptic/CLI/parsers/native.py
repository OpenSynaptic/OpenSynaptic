"""Parsers for native toolchain and Rust core build commands.

Commands registered here:
  native-check, native-build, rscore-build, rscore-check
"""
import argparse


def register(sub: argparse._SubParsersAction) -> None:
    """Attach native/build commands to *sub*."""

    # --- native-check ---
    native_check = sub.add_parser(
        'native-check', aliases=['os-native-check'],
        help='Check native compiler/toolchain availability before building C bindings',
    )
    native_check.add_argument('--json', action='store_true', default=False,
                              help='Output precheck report as JSON')
    native_check.add_argument('--timeout', type=float, default=8.0,
                              help='Timeout in seconds for toolchain precheck')

    # --- native-build ---
    native_build = sub.add_parser(
        'native-build', aliases=['os-native-build'],
        help='Build native C bindings with real-time compiler output streaming',
    )
    native_build.add_argument('--json', action='store_true', default=False,
                              help='Output build result as JSON')
    native_build.add_argument('--no-progress', action='store_true', default=False,
                              help='Disable real-time compile output stream')
    native_build.add_argument('--idle-timeout', type=float, default=20.0,
                              help='Timeout in seconds when compiler produces no output')
    native_build.add_argument('--max-timeout', type=float, default=300.0,
                              help='Maximum compile time per target in seconds')
    native_build.add_argument('--include-rscore', action='store_true', default=False,
                              help='Also compile the Rust RSCore crate after building C targets')

    # --- rscore-build ---
    rscore_build = sub.add_parser(
        'rscore-build', aliases=['os-rscore-build'],
        help='Compile the Rust RSCore crate and install os_rscore DLL',
    )
    rscore_build.add_argument('--json', action='store_true', default=False,
                              help='Output build result as JSON')
    rscore_build.add_argument('--no-progress', action='store_true', default=False,
                              help='Disable cargo output stream')
    rscore_build.add_argument('--debug', action='store_true', default=False,
                              help='Build a debug (unoptimised) DLL instead of release')

    # --- rscore-check ---
    rscore_check = sub.add_parser(
        'rscore-check', aliases=['os-rscore-check'],
        help='Report RSCore Rust DLL availability and active codec backend',
    )
    rscore_check.add_argument('--json', action='store_true', default=False,
                              help='Output status as JSON')

