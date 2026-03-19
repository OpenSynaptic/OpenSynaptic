import ctypes

from opensynaptic.utils.c.native_loader import require_native_library


class Base62Codec:

    def __init__(self, precision=4):
        self.precision_val = 10 ** precision
        self._lib = require_native_library('os_base62')
        self._lib.os_b62_encode_i64.argtypes = [ctypes.c_longlong, ctypes.c_char_p, ctypes.c_size_t]
        self._lib.os_b62_encode_i64.restype = ctypes.c_int
        self._lib.os_b62_decode_i64.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]
        self._lib.os_b62_decode_i64.restype = ctypes.c_longlong

    def encode(self, n, use_precision=True):
        try:
            val = int(round(float(n) * self.precision_val)) if use_precision else int(float(n))
        except Exception:
            return '0'
        out = ctypes.create_string_buffer(128)
        ok = self._lib.os_b62_encode_i64(int(val), out, ctypes.sizeof(out))
        if int(ok) != 1:
            raise RuntimeError('native base62 encode failed')
        return out.value.decode('ascii')

    def decode(self, s, use_precision=True):
        if not s or s == '0':
            return 0.0
        ok = ctypes.c_int(0)
        raw = self._lib.os_b62_decode_i64(str(s).encode('ascii'), ctypes.byref(ok))
        if int(ok.value) != 1:
            raise RuntimeError('native base62 decode failed')
        decoded_int = int(raw)
        if not use_precision:
            return float(decoded_int)
        return round(decoded_int / self.precision_val, 8)
