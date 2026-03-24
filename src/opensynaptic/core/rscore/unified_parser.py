from opensynaptic.core.common.base import BaseOSVisualFusionEngine
from opensynaptic.core.rscore._ffi_proxy import RsFFIProxyBase


class OSVisualFusionEngine(BaseOSVisualFusionEngine, RsFFIProxyBase):
    def __init__(self, *args, **kwargs):
        self._init_ffi('RsOSVisualFusionEngine', 'Rust fusion engine is unavailable', *args, **kwargs)
        ffi = self._require_ffi('Rust fusion engine is unavailable')
        self._ffi_run_engine = ffi.run_engine
        self._ffi_decompress = ffi.decompress
        self._ffi_relay = ffi.relay

    def run_engine(self, *args, **kwargs):
        return self._ffi_run_engine(*args, **kwargs)

    def decompress(self, *args, **kwargs):
        return self._ffi_decompress(*args, **kwargs)

    def relay(self, *args, **kwargs):
        return self._ffi_relay(*args, **kwargs)
