from opensynaptic.core.common.base import BaseOSHandshakeManager, NativeLibraryUnavailable


class CMD:
    DATA_FULL = 63
    DATA_FULL_SEC = 64
    DATA_DIFF = 170
    DATA_DIFF_SEC = 171
    DATA_HEART = 127
    DATA_HEART_SEC = 128
    ID_REQUEST = 1
    ID_ASSIGN = 2
    ID_POOL_REQ = 3
    ID_POOL_RES = 4
    HANDSHAKE_ACK = 5
    HANDSHAKE_NACK = 6
    PING = 9
    PONG = 10
    TIME_REQUEST = 11
    TIME_RESPONSE = 12
    SECURE_DICT_READY = 13
    SECURE_CHANNEL_ACK = 14

    DATA_CMDS = {DATA_FULL, DATA_FULL_SEC, DATA_DIFF, DATA_DIFF_SEC, DATA_HEART, DATA_HEART_SEC}
    PLAIN_DATA_CMDS = {DATA_FULL, DATA_DIFF, DATA_HEART}
    SECURE_DATA_CMDS = {DATA_FULL_SEC, DATA_DIFF_SEC, DATA_HEART_SEC}
    CTRL_CMDS = {
        ID_REQUEST,
        ID_ASSIGN,
        ID_POOL_REQ,
        ID_POOL_RES,
        HANDSHAKE_ACK,
        HANDSHAKE_NACK,
        PING,
        PONG,
        TIME_REQUEST,
        TIME_RESPONSE,
        SECURE_DICT_READY,
        SECURE_CHANNEL_ACK,
    }
    BASE_DATA_CMD = {DATA_FULL_SEC: DATA_FULL, DATA_DIFF_SEC: DATA_DIFF, DATA_HEART_SEC: DATA_HEART}
    SECURE_DATA_CMD = {DATA_FULL: DATA_FULL_SEC, DATA_DIFF: DATA_DIFF_SEC, DATA_HEART: DATA_HEART_SEC}


class OSHandshakeManager(BaseOSHandshakeManager):
    def __init__(self, *args, **kwargs):
        self._ffi = None
        self._rs_cmd_is_data = None
        self._rs_cmd_normalize = None
        self._rs_cmd_secure = None
        try:
            from opensynaptic.core.rscore import codec as rs_codec

            self._rs_cmd_is_data = getattr(rs_codec, "cmd_is_data", None)
            self._rs_cmd_normalize = getattr(rs_codec, "cmd_normalize_data", None)
            self._rs_cmd_secure = getattr(rs_codec, "cmd_secure_variant", None)
            ctor = getattr(rs_codec, "RsOSHandshakeManager", None)
            if not callable(ctor) or (not rs_codec.has_rs_native()):
                raise NativeLibraryUnavailable("Rust native library not loaded")
            self._ffi = ctor(*args, **kwargs)
        except Exception as e:
            self._ffi = None
            raise NativeLibraryUnavailable("Rust handshake manager is unavailable") from e

    def negotiate(self, *args, **kwargs):
        if not self._ffi:
            raise NativeLibraryUnavailable("Rust native library not loaded")
        return self._ffi.negotiate(*args, **kwargs)

    def is_secure_data_cmd(self, cmd):
        fn = self._rs_cmd_normalize
        if callable(fn):
            try:
                return int(cmd) != int(fn(int(cmd) & 0xFF))
            except Exception:
                pass
        return int(cmd) in CMD.SECURE_DATA_CMDS

    def normalize_data_cmd(self, cmd):
        fn = self._rs_cmd_normalize
        if callable(fn):
            try:
                return int(fn(int(cmd) & 0xFF))
            except Exception:
                pass
        return CMD.BASE_DATA_CMD.get(int(cmd), int(cmd))

    def secure_variant_cmd(self, cmd):
        fn = self._rs_cmd_secure
        if callable(fn):
            try:
                return int(fn(int(cmd) & 0xFF))
            except Exception:
                pass
        return CMD.SECURE_DATA_CMD.get(int(cmd), int(cmd))

    def __getattr__(self, name):
        ffi = self.__dict__.get("_ffi")
        if ffi is not None and hasattr(ffi, name):
            return getattr(ffi, name)
        raise AttributeError(f"{self.__class__.__name__} has no attribute '{name}'")
