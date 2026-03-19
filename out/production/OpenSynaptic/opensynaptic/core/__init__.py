from opensynaptic.core.coremanager import CoreManager, get_core_manager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opensynaptic.core.pycore.core import OpenSynaptic
    from opensynaptic.core.pycore.handshake import CMD, OSHandshakeManager
    from opensynaptic.core.pycore.solidity import OpenSynapticEngine
    from opensynaptic.core.pycore.standardization import OpenSynapticStandardizer
    from opensynaptic.core.pycore.transporter_manager import TransporterManager
    from opensynaptic.core.pycore.unified_parser import OSVisualFusionEngine

_PUBLIC_SYMBOLS = {
    'OpenSynaptic',
    'OpenSynapticStandardizer',
    'OpenSynapticEngine',
    'OSVisualFusionEngine',
    'OSHandshakeManager',
    'CMD',
    'TransporterManager',
}

__all__ = [
    'CoreManager',
    'get_core_manager',
    'OpenSynaptic',
    'OpenSynapticStandardizer',
    'OpenSynapticEngine',
    'OSVisualFusionEngine',
    'OSHandshakeManager',
    'CMD',
    'TransporterManager',
]


def __getattr__(name):
    if name in _PUBLIC_SYMBOLS:
        return get_core_manager().get_symbol(name)
    raise AttributeError("module 'opensynaptic.core' has no attribute '{}'".format(name))

