from .api import (
    CMD,
    OSHandshakeManager,
    OSVisualFusionEngine,
    OpenSynaptic,
    OpenSynapticEngine,
    OpenSynapticStandardizer,
    TransporterManager,
    rs_native_available,
)

# Optional capability probes (degrade gracefully when DLL is absent / older).
def _probe_crc() -> bool:
    try:
        from opensynaptic.core.rscore.codec import has_crc_helpers
        return has_crc_helpers()
    except Exception:
        return False


def _probe_header_parser() -> bool:
    try:
        from opensynaptic.core.rscore.codec import has_header_parser
        return has_header_parser()
    except Exception:
        return False


def _probe_auto_decompose() -> bool:
    try:
        from opensynaptic.core.rscore.codec import has_auto_decompose
        return has_auto_decompose()
    except Exception:
        return False


def _probe_solidity_compressor() -> bool:
    try:
        from opensynaptic.core.rscore.codec import has_solidity_compressor
        return has_solidity_compressor()
    except Exception:
        return False


def _probe_fusion_state() -> bool:
    try:
        from opensynaptic.core.rscore.codec import has_fusion_state
        return has_fusion_state()
    except Exception:
        return False


CORE_PLUGIN = {
    'name': 'rscore',
    'kind': 'core',
    'backend': 'rust-hybrid',
    'rs_native': rs_native_available(),
    'rs_crc': _probe_crc(),
    'rs_header_parser': _probe_header_parser(),
    'rs_auto_decompose': _probe_auto_decompose(),
    'rs_solidity_compressor': _probe_solidity_compressor(),
    'rs_fusion_state': _probe_fusion_state(),
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
    'rs_native_available',
]
