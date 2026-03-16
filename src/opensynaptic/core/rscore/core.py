# rscore is glue-only; protocol logic lives in Rust FFI.
from pathlib import Path

from opensynaptic.core.common.base import BaseOpenSynaptic, NativeLibraryUnavailable
from opensynaptic.services import ServiceManager
from opensynaptic.utils import ctx, read_json, write_json


class OpenSynaptic(BaseOpenSynaptic):
    def __init__(self, *args, **kwargs):
        config_path = kwargs.get('config_path')
        if config_path is None and args:
            config_path = args[0]
        if config_path:
            self.config_path = str(Path(config_path).resolve())
            self.base_dir = str(Path(self.config_path).parent)
            self.config = read_json(self.config_path) or {}
        else:
            self.base_dir = str(ctx.root)
            self.config_path = str(Path(self.base_dir) / 'Config.json')
            self.config = dict(ctx.config or {})

        self._ffi = None
        try:
            from opensynaptic.core.rscore import codec as rs_codec

            ctor = getattr(rs_codec, "RsOpenSynaptic", None)
            if not callable(ctor) or (not rs_codec.has_rs_native()):
                raise NativeLibraryUnavailable("Rust native library not loaded")
            self._ffi = ctor(*args, **kwargs)
        except Exception as e:
            self._ffi = None
            raise NativeLibraryUnavailable("Rust node facade is unavailable") from e

        from opensynaptic.core.rscore.handshake import OSHandshakeManager
        from opensynaptic.core.rscore.solidity import OpenSynapticEngine
        from opensynaptic.core.rscore.standardization import OpenSynapticStandardizer
        from opensynaptic.core.rscore.transporter_manager import TransporterManager
        from opensynaptic.core.rscore.unified_parser import OSVisualFusionEngine

        self.standardizer = OpenSynapticStandardizer(*args, **kwargs)
        self.engine = OpenSynapticEngine(*args, **kwargs)
        self.fusion = OSVisualFusionEngine(*args, **kwargs)
        self.protocol = OSHandshakeManager(*args, **kwargs)
        self.transporter_manager = TransporterManager(*args, **kwargs)
        self.service_manager = ServiceManager(config=self.config, mode='runtime')
        self.active_transporters = {}
        self.assigned_id = getattr(self._ffi, 'assigned_id', None)
        self.device_id = getattr(self._ffi, 'device_id', None)

        # Keep config-assigned id available for CLI/plugin flows.
        cfg_aid = self.config.get('assigned_id') if isinstance(self.config, dict) else None
        if self.assigned_id in (None, '') and cfg_aid not in (None, ''):
            self.assigned_id = cfg_aid

    def _save_config(self):
        if not self.config_path:
            return
        try:
            write_json(self.config_path, self.config, indent=4)
        except Exception:
            return

    def ensure_id(self, server_ip=None, server_port=None, device_meta=None, *args, **kwargs):
        if not self._ffi:
            raise NativeLibraryUnavailable("Rust node facade is unavailable")
        return self._ffi.ensure_id(server_ip, server_port, device_meta, *args, **kwargs)

    def transmit(self, sensors=None, device_id=None, device_status="ONLINE", **kwargs):
        if not self._ffi:
            raise NativeLibraryUnavailable("Rust node facade is unavailable")
        if 'assigned_id' not in kwargs:
            kwargs['assigned_id'] = getattr(self, 'assigned_id', None)
        try:
            return self._ffi.transmit(sensors=sensors, device_id=device_id, device_status=device_status, **kwargs)
        except TypeError:
            return self._ffi.transmit(sensors, device_id, device_status, **kwargs)

    def dispatch(self, packet, medium="UDP", *args, **kwargs):
        if not self._ffi:
            raise NativeLibraryUnavailable("Rust node facade is unavailable")
        return self._ffi.dispatch(packet, medium, *args, **kwargs)

    def _sync_assigned_id_to_fusion(self):
        aid = getattr(self, 'assigned_id', None)
        if aid in (None, ""):
            return None
        set_local = getattr(self.fusion, '_set_local_id', None)
        if callable(set_local):
            try:
                set_local(int(aid))
                return None
            except Exception:
                return None
        try:
            self.fusion.local_id = int(aid)
            self.fusion.local_id_str = str(int(aid))
        except Exception:
            return None

