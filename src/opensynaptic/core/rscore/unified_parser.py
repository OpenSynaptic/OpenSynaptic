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

    @staticmethod
    def _normalize_meta(decoded):
        if not isinstance(decoded, dict):
            return decoded
        meta = decoded.get('__packet_meta__')
        if not isinstance(meta, dict):
            return decoded

        patched = dict(meta)
        changed = False

        tid = patched.get('tid')
        if isinstance(tid, int):
            patched['tid'] = str(tid).zfill(2)
            changed = True
        elif isinstance(tid, str) and tid.isdigit() and len(tid) < 2:
            patched['tid'] = str(int(tid)).zfill(2)
            changed = True

        if ('crc8_ok' not in patched) and ('error' not in decoded):
            base_cmd = int(patched.get('base_cmd', patched.get('cmd', 0)) or 0)
            if base_cmd in (63, 127, 170):
                patched['crc8_ok'] = True
                changed = True

        if changed:
            decoded['__packet_meta__'] = patched
        return decoded

    def decompress(self, *args, **kwargs):
        decoded = self._ffi_decompress(*args, **kwargs)
        return self._normalize_meta(decoded)

    def relay(self, *args, **kwargs):
        return self._ffi_relay(*args, **kwargs)
