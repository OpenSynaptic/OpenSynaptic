# rscore is glue-only; protocol logic lives in Rust FFI.
from opensynaptic.core.common.base import BaseTransporterManager, NativeLibraryUnavailable


class TransporterManager(BaseTransporterManager):
    def __init__(self, *args, **kwargs):
        self._ffi = None
        try:
            from opensynaptic.core.rscore import codec as rs_codec

            ctor = getattr(rs_codec, "RsTransporterManager", None)
            if not callable(ctor) or (not rs_codec.has_rs_native()):
                raise NativeLibraryUnavailable("Rust native library not loaded")
            self._ffi = ctor(*args, **kwargs)
        except Exception as e:
            self._ffi = None
            raise NativeLibraryUnavailable("Rust transporter manager is unavailable") from e

    def send(self, payload, config):
        if not self._ffi:
            raise NativeLibraryUnavailable("Rust native library not loaded")
        return self._ffi.send(payload, config)

    def listen(self, config, callback):
        if not self._ffi:
            raise NativeLibraryUnavailable("Rust native library not loaded")
        return self._ffi.listen(config, callback)

    def __getattr__(self, name):
        ffi = self.__dict__.get("_ffi")
        if ffi is not None and hasattr(ffi, name):
            return getattr(ffi, name)
        raise AttributeError(f"{self.__class__.__name__} has no attribute '{name}'")
