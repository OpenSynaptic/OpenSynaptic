# rscore is glue-only; protocol logic lives in Rust FFI.
from opensynaptic.core.common.base import BaseTransporterManager
from opensynaptic.core.rscore._ffi_proxy import RsFFIProxyBase


class TransporterManager(BaseTransporterManager, RsFFIProxyBase):
    def __init__(self, *args, **kwargs):
        self._init_ffi('RsTransporterManager', 'Rust transporter manager is unavailable', *args, **kwargs)
        self.active_transporters = {}

    def send(self, payload, config):
        return self._require_ffi('Rust native library not loaded').send(payload, config)

    def listen(self, config, callback):
        return self._require_ffi('Rust native library not loaded').listen(config, callback)

    def auto_load(self):
        # Keep API parity with pycore manager. Rust path currently exposes no dynamic discovery.
        return self.active_transporters

    def runtime_tick(self):
        # CLI run-loop calls this periodically; no-op until Rust transporter runtime ABI is added.
        return True

    def _normalize_medium(self, medium):
        return str(medium or '').strip().lower()

    def refresh_protocol(self, medium):
        # Keep method parity with pycore. Rust driver hot-reload is not implemented yet.
        _ = self._normalize_medium(medium)
        return None

    def get_driver(self, medium):
        return None

    def dispatch_auto(self, packet):
        return (False, None)

