"""RSCore standalone API facade.

This module intentionally imports only rscore-local implementations so
`opensynaptic.core.rscore` has no direct dependency on `pycore`.
"""

from opensynaptic.core.rscore.core import OpenSynaptic
from opensynaptic.core.rscore.handshake import CMD, OSHandshakeManager
from opensynaptic.core.rscore.solidity import OpenSynapticEngine
from opensynaptic.core.rscore.standardization import OpenSynapticStandardizer
from opensynaptic.core.rscore.transporter_manager import TransporterManager
from opensynaptic.core.rscore.unified_parser import OSVisualFusionEngine
from opensynaptic.core.rscore.codec import has_rs_native


def rs_native_available() -> bool:
    """Return True when the Rust RS core native library is available."""
    try:
        return bool(has_rs_native())
    except Exception:
        return False


__all__ = [
    'OpenSynaptic',
    'OpenSynapticStandardizer',
    'OpenSynapticEngine',
    'OSVisualFusionEngine',
    'OSHandshakeManager',
    'CMD',
    'TransporterManager',
    'rs_native_available',
]

