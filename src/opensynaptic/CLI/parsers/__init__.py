"""OpenSynaptic CLI parser sub-package.

Each module exports a single ``register(sub)`` function that attaches
its commands to an :class:`argparse._SubParsersAction`.  The top-level
assembler lives in :mod:`opensynaptic.CLI.build_parser`.
"""
from . import core, config, test, plugin, native, service, extra

__all__ = ['core', 'config', 'test', 'plugin', 'native', 'service', 'extra']

