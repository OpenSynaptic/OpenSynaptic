from .core import OpenSynaptic
from .standardization import OpenSynapticStandardizer
from .solidity import OpenSynapticEngine
from .unified_parser import OSVisualFusionEngine
from .handshake import OSHandshakeManager, CMD
from .transporter_manager import TransporterManager

CORE_PLUGIN = {
    'name': 'pycore',
    'kind': 'core',
    'symbols': {
        'OpenSynaptic': OpenSynaptic,
        'OpenSynapticStandardizer': OpenSynapticStandardizer,
        'OpenSynapticEngine': OpenSynapticEngine,
        'OSVisualFusionEngine': OSVisualFusionEngine,
        'OSHandshakeManager': OSHandshakeManager,
        'CMD': CMD,
        'TransporterManager': TransporterManager,
    },
}


def get_core_plugin():
    return CORE_PLUGIN

__all__ = [
    'OpenSynaptic',
    'OpenSynapticStandardizer',
    'OpenSynapticEngine',
    'OSVisualFusionEngine',
    'OSHandshakeManager',
    'CMD',
    'TransporterManager',
    'CORE_PLUGIN',
    'get_core_plugin',
]

