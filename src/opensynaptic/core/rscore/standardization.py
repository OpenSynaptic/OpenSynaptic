# rscore is glue-only; protocol logic lives in Rust FFI.
from opensynaptic.core.common.base import BaseOpenSynapticStandardizer, NativeLibraryUnavailable


class OpenSynapticStandardizer(BaseOpenSynapticStandardizer):
    def __init__(self, *args, **kwargs):
        self._ffi = None
        try:
            from opensynaptic.core.rscore import codec as rs_codec

            ctor = getattr(rs_codec, "RsOpenSynapticStandardizer", None)
            if not callable(ctor) or (not rs_codec.has_rs_native()):
                raise NativeLibraryUnavailable("Rust native library not loaded")
            self._ffi = ctor(*args, **kwargs)
        except Exception as e:
            self._ffi = None
            raise NativeLibraryUnavailable("Rust standardizer is unavailable") from e

    def standardize(self, *args, **kwargs):
        if not self._ffi:
            raise NativeLibraryUnavailable("Rust native library not loaded")
        return self._ffi.standardize(*args, **kwargs)

    def __getattr__(self, name):
        ffi = self.__dict__.get("_ffi")
        if ffi is not None and hasattr(ffi, name):
            return getattr(ffi, name)
        raise AttributeError(f"{self.__class__.__name__} has no attribute '{name}'")
