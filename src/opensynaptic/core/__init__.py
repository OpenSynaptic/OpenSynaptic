from opensynaptic.core.coremanager import CoreManager, get_core_manager

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

