"""Shared Rust FFI proxy utilities for rscore wrapper classes."""

from __future__ import annotations

from opensynaptic.core.common.base import NativeLibraryUnavailable


def load_rs_codec():
    from opensynaptic.core.rscore import codec as rs_codec
    return rs_codec


class RsFFIProxyBase:
    """Mixin that centralizes Rust FFI ctor loading and proxy forwarding."""

    _ffi = None

    def _init_ffi(self, ctor_name, unavailable_msg, *args, **kwargs):
        try:
            rs_codec = load_rs_codec()
            ctor = getattr(rs_codec, ctor_name, None)
            if not callable(ctor) or (not rs_codec.has_rs_native()):
                raise NativeLibraryUnavailable("Rust native library not loaded")
            self._ffi = ctor(*args, **kwargs)
            return rs_codec
        except Exception as e:
            self._ffi = None
            raise NativeLibraryUnavailable(unavailable_msg) from e

    def _require_ffi(self, unavailable_msg):
        if not self._ffi:
            raise NativeLibraryUnavailable(unavailable_msg)
        return self._ffi

    def __getattr__(self, name):
        ffi = self.__dict__.get('_ffi')
        if ffi is not None and hasattr(ffi, name):
            return getattr(ffi, name)
        raise AttributeError(f"{self.__class__.__name__} has no attribute '{name}'")

