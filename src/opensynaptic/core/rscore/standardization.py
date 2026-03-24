# rscore is glue-only; protocol logic lives in Rust FFI.
from opensynaptic.core.common.base import BaseOpenSynapticStandardizer
from opensynaptic.core.rscore._ffi_proxy import RsFFIProxyBase


class OpenSynapticStandardizer(BaseOpenSynapticStandardizer, RsFFIProxyBase):
    def __init__(self, *args, **kwargs):
        self._init_ffi('RsOpenSynapticStandardizer', 'Rust standardizer is unavailable', *args, **kwargs)
        ffi = self._require_ffi('Rust native library not loaded')
        self._ffi_standardize = ffi.standardize

    def standardize(self, *args, **kwargs):
        return self._ffi_standardize(*args, **kwargs)
