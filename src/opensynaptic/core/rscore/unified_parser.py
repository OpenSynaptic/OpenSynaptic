from opensynaptic.core.common.base import BaseOSVisualFusionEngine, NativeLibraryUnavailable


class OSVisualFusionEngine(BaseOSVisualFusionEngine):
    def __init__(self, *args, **kwargs):
        self._ffi = None
        try:
            from opensynaptic.core.rscore import codec as rs_codec

            ctor = getattr(rs_codec, "RsOSVisualFusionEngine", None)
            if not callable(ctor) or (not rs_codec.has_rs_native()):
                raise NativeLibraryUnavailable("Rust native library not loaded")
            self._ffi = ctor(*args, **kwargs)
        except Exception as e:
            self._ffi = None
            raise NativeLibraryUnavailable("Rust fusion engine is unavailable") from e

    def run_engine(self, *args, **kwargs):
        if not self._ffi:
            raise NativeLibraryUnavailable("Rust fusion engine is unavailable")
        return self._ffi.run_engine(*args, **kwargs)

    def decompress(self, *args, **kwargs):
        if not self._ffi:
            raise NativeLibraryUnavailable("Rust fusion engine is unavailable")
        return self._ffi.decompress(*args, **kwargs)

    def relay(self, *args, **kwargs):
        if not self._ffi:
            raise NativeLibraryUnavailable("Rust fusion engine is unavailable")
        return self._ffi.relay(*args, **kwargs)

    def __getattr__(self, name):
        ffi = self.__dict__.get("_ffi")
        if ffi is not None and hasattr(ffi, name):
            return getattr(ffi, name)
        raise AttributeError(f"{self.__class__.__name__} has no attribute '{name}'")
