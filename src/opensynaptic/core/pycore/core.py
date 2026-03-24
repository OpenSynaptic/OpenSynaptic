import socket
import time
import threading
from pathlib import Path
from .standardization import OpenSynapticStandardizer
from .solidity import OpenSynapticEngine
from .unified_parser import OSVisualFusionEngine
from .handshake import OSHandshakeManager, CMD
from .transporter_manager import TransporterManager
from opensynaptic.services import ServiceManager
from opensynaptic.services.plugin_registry import sync_all_plugin_defaults, autoload_enabled_plugins
from opensynaptic.utils import (
    read_json,
    write_json,
    ctx,
    os_log,
    LogMsg,
    NativeLibraryUnavailable,
    payload_len,
)
from opensynaptic.utils.buffer import to_wire_payload
try:
    from opensynaptic.services.db_engine import DatabaseManager
except Exception:
    DatabaseManager = None
try:
    from plugins.id_allocator import IDAllocator
except ImportError:
    import sys
    # pycore/core.py is one level deeper than the old core.py layout.
    sys.path.append(str(Path(__file__).resolve().parents[4]))
    from plugins.id_allocator import IDAllocator

class OpenSynaptic:
    MAX_UINT32 = 4294967295

    def __init__(self, config_path=None):
        if config_path:
            self.config_path = config_path
            self.config = self._load_json(self.config_path)
            self.base_dir = str(Path(self.config_path).resolve().parent)
        else:
            self.config = ctx.config or {}
            self.config_path = str(Path(ctx.root) / 'Config.json')
            self.base_dir = ctx.root
        self.settings = self.config.get('OpenSynaptic_Setting', {})
        self.res_conf = self.config.get('RESOURCES', {})
        self.security_settings = self.config.get('security_settings', {})
        self._config_lock = threading.Lock()
        self._lease_metrics_last_flush = 0
        self._lease_metrics_flush_interval = 10
        self._registry_sync_lock = threading.Lock()
        self._registry_last_sync = {}
        engine_cfg = self.config.get('engine_settings', {}) if isinstance(self.config.get('engine_settings', {}), dict) else {}
        self._registry_sync_interval_seconds = max(0.0, float(engine_cfg.get('registry_sync_interval_seconds', 1.0) or 1.0))
        self.assigned_id = self.config.get('assigned_id', None)
        self.device_id = self.config.get('device_id', 'UNKNOWN')
        self.standardizer = OpenSynapticStandardizer(self.config_path)
        try:
            self.engine = OpenSynapticEngine(self.config_path)
        except NativeLibraryUnavailable:
            # C-only Base62 path: bubble up a single clear failure.
            raise
        except Exception as e:
            os_log.err('ENG', 'INIT', e, {'cfg': self.config_path})
            self.engine = OpenSynapticEngine()
        self.fusion = OSVisualFusionEngine(self.config_path)
        self._sync_assigned_id_to_fusion()
        start_id = int(self.config.get('Server_Core', {}).get('Start_ID', 1))
        end_id = int(self.config.get('Server_Core', {}).get('End_ID', 4294967295))

        lease_cfg, lease_changed = self._resolve_id_lease_config()
        self._lease_metrics_flush_interval = max(1, int(lease_cfg.get('metrics_flush_seconds', 10) or 10))
        self.id_allocator = IDAllocator(
            base_dir=self.base_dir,
            start_id=start_id,
            end_id=end_id,
            persist_file=str(lease_cfg.get('persist_file', 'data/id_allocation.json')),
            lease_policy={
                'offline_hold_days': lease_cfg.get('offline_hold_days', 30),
                'base_lease_seconds': lease_cfg.get('base_lease_seconds', 2592000),
                'min_lease_seconds': lease_cfg.get('min_lease_seconds', 0),
                'rate_window_seconds': lease_cfg.get('rate_window_seconds', 3600),
                'high_rate_threshold_per_hour': lease_cfg.get('high_rate_threshold_per_hour', 60.0),
                'ultra_rate_threshold_per_hour': lease_cfg.get('ultra_rate_threshold_per_hour', 180.0),
                'ultra_rate_sustain_seconds': lease_cfg.get('ultra_rate_sustain_seconds', 600),
                'high_rate_min_factor': lease_cfg.get('high_rate_min_factor', 0.2),
                'adaptive_enabled': lease_cfg.get('adaptive_enabled', True),
                'ultra_force_release': lease_cfg.get('ultra_force_release', True),
                'metrics_emit_interval_seconds': lease_cfg.get('metrics_emit_interval_seconds', 5),
            },
            metrics_sink=self._on_id_lease_metrics,
        )

        registry_dir = getattr(ctx, 'registry_dir', None) or str(Path(self.base_dir) / 'data' / 'device_registry')
        Path(registry_dir).mkdir(parents=True, exist_ok=True)

        secure_store_path = str(self.security_settings.get('secure_session_store', 'data/secure_sessions.json') or 'data/secure_sessions.json')
        if not Path(secure_store_path).is_absolute():
            secure_store_path = str(Path(self.base_dir) / secure_store_path)
        self.protocol = OSHandshakeManager(
            target_sync_count=3,
            registry_dir=registry_dir,
            expire_seconds=int(self.security_settings.get('secure_session_expire_seconds', 86400)),
            secure_store_path=secure_store_path,
        )
        self.protocol.min_valid_timestamp = int(self.security_settings.get('time_sync_threshold', self.protocol.min_valid_timestamp))
        self.protocol.id_allocator = self.id_allocator
        self.protocol.parser = self.fusion
        try:
            self.fusion.protocol = self.protocol
        except Exception as e:
            os_log.err('FUS', 'ASSIGN', e, {})
        self.active_transporters = {}
        self.db_manager = None
        self.service_manager = ServiceManager(config=self.config, mode='runtime')
        try:
            if sync_all_plugin_defaults(self.config):
                self._save_config()
        except Exception as e:
            os_log.err('SVC', 'CFG_SYNC', e, {})
        try:
            self.transporter_manager = TransporterManager(self)
            self.transporter_manager.auto_load()
            self.active_transporters = self.transporter_manager.active_transporters
        except Exception as e:
            os_log.err('TM', 'INIT', e, {})
        try:
            autoload_enabled_plugins(self, mode='runtime', auto_start_only=True)
        except Exception as e:
            os_log.err('SVC', 'AUTOLOAD', e, {})
        if lease_changed:
            self._save_config()
        os_log.log_with_const('info', LogMsg.READY, root=self.base_dir)
        if DatabaseManager:
            try:
                self.db_manager = DatabaseManager.from_opensynaptic_config(self.config)
                if self.db_manager:
                    self.service_manager.mount('db_engine', self.db_manager, config=self.config.get('storage', {}).get('sql', {}), mode='runtime')
                    self.service_manager.load('db_engine')
            except Exception as e:
                os_log.err('DB', 'INIT', e, {})

    def _normalize_assigned_id(self, aid):
        if aid is None or aid == '' or aid == 'UNKNOWN':
            return 0
        if isinstance(aid, int):
            return 0 if aid == self.MAX_UINT32 else aid
        if isinstance(aid, str) and aid.isdigit():
            value = int(aid)
            return 0 if value == self.MAX_UINT32 else value
        if isinstance(aid, str) and aid:
            return self.fusion._decode_b62(aid)
        return 0

    def _apply_fusion_local_id(self, value):
        set_local_id = getattr(self.fusion, '_set_local_id', None)
        if callable(set_local_id):
            set_local_id(value)
        else:
            self.fusion.local_id = value
            self.fusion.local_id_str = str(value)

    def _sync_assigned_id_to_fusion(self):
        try:
            self._apply_fusion_local_id(self._normalize_assigned_id(self.assigned_id))
        except Exception as e:
            os_log.err('FUS', 'SYNC', e, {})
            self._apply_fusion_local_id(0)

    def _is_id_missing(self):
        return self._normalize_assigned_id(self.assigned_id) == 0

    def _resolve_server_endpoint(self, server_ip=None, server_port=None):
        client_cfg = self.config.get('Client_Core', {})
        host = server_ip or client_cfg.get('server_host') or '127.0.0.1'
        port = int(server_port or client_cfg.get('server_port') or self.config.get('Server_Core', {}).get('port', 8080))
        return (host, port)

    def _save_config(self):
        try:
            write_json(self.config_path, self.config, indent=4)
        except Exception as e:
            os_log.err('CFG', 'WRITE', e, {'path': self.config_path})

    def _resolve_id_lease_config(self):
        sec = self.config.setdefault('security_settings', {})
        lease_cfg = sec.setdefault('id_lease', {})
        defaults = {
            'persist_file': 'data/id_allocation.json',
            'offline_hold_days': 30,
            'base_lease_seconds': 30 * 86400,
            'min_lease_seconds': 0,
            'rate_window_seconds': 3600,
            'high_rate_threshold_per_hour': 60.0,
            'ultra_rate_threshold_per_hour': 180.0,
            'ultra_rate_sustain_seconds': 600,
            'high_rate_min_factor': 0.2,
            'adaptive_enabled': True,
            'ultra_force_release': True,
            'metrics_emit_interval_seconds': 5,
            'metrics_flush_seconds': 10,
            'metrics': {},
        }
        changed = False
        for key, value in defaults.items():
            if key not in lease_cfg:
                lease_cfg[key] = value
                changed = True
        return lease_cfg, changed

    def _on_id_lease_metrics(self, metrics):
        if not isinstance(metrics, dict):
            return
        now_ts = int(time.time())
        with self._config_lock:
            sec = self.config.setdefault('security_settings', {})
            lease_cfg = sec.setdefault('id_lease', {})
            lease_cfg['metrics'] = dict(metrics)
            lease_cfg['metrics_updated_at'] = now_ts
            if now_ts - int(self._lease_metrics_last_flush or 0) >= self._lease_metrics_flush_interval:
                self._save_config()
                self._lease_metrics_last_flush = now_ts

    def _load_json(self, path):
        return read_json(path)

    def _to_wire_payload(self, payload, config=None, force_zero_copy=False):
        active_cfg = config if isinstance(config, dict) else self.config
        return to_wire_payload(payload, active_cfg, force_zero_copy=force_zero_copy)

    def _maybe_sync_registry(self, src_aid, reg, force=False):
        if not reg or (not reg.get('dirty')):
            return
        now = time.time()
        key = str(src_aid)
        with self._registry_sync_lock:
            last = float(self._registry_last_sync.get(key, 0.0) or 0.0)
            if (not force) and (now - last < self._registry_sync_interval_seconds):
                return
            self._registry_last_sync[key] = now
        self.fusion._sync_to_disk(src_aid)

    def _run_udp_exchange(self, host, port, timeout, request_fn):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)

        def send_fn(data):
            sock.sendto(data, (host, port))

        def recv_fn(timeout=1.0):
            sock.settimeout(timeout)
            try:
                data, _ = sock.recvfrom(4096)
                return data
            except socket.timeout:
                return None

        try:
            return request_fn(send_fn, recv_fn)
        finally:
            sock.close()

    def ensure_id(self, server_ip, server_port, device_meta=None, timeout=5.0):
        if not self._is_id_missing():
            os_log.log_with_const('info', LogMsg.ID_ASSIGNED, addr=self.device_id, assigned=self.assigned_id)
            return True
        os_log.log_with_const('info', LogMsg.ID_REQUEST_TIMEOUT, timeout=0)
        meta = device_meta or {}
        meta['device_id'] = self.device_id
        def _request(send_fn, recv_fn):
            return self.protocol.request_id_via_transport(
                transport_send_fn=send_fn,
                transport_recv_fn=recv_fn,
                device_meta=meta,
                timeout=timeout,
            )
        new_id = self._run_udp_exchange(server_ip, server_port, timeout, _request)
        if new_id:
            os_log.log_with_const('info', LogMsg.ID_ASSIGNED, addr=self.device_id, assigned=new_id)
            self.assigned_id = new_id
            self.config['assigned_id'] = new_id
            self._save_config()
            self._sync_assigned_id_to_fusion()
            os_log.log_with_const('info', LogMsg.CONFIG_SAVED, field='assigned_id', value=new_id)
            return True
        else:
            os_log.log_with_const('error', LogMsg.FAILED_SEND, info=f'ID request failed for {self.device_id}')
            return False

    def ensure_time(self, server_ip=None, server_port=None, timeout=3.0):
        host, port = self._resolve_server_endpoint(server_ip, server_port)
        def _request(send_fn, recv_fn):
            return self.protocol.request_time_via_transport(
                transport_send_fn=send_fn,
                transport_recv_fn=recv_fn,
                timeout=timeout,
            )
        server_time = self._run_udp_exchange(host, port, timeout, _request)
        if server_time:
            self.protocol.note_server_time(server_time)
            os_log.log_with_const('info', LogMsg.TIME_SYNCED, server_time=server_time, host=host, port=port)
        return server_time

    def dispatch_with_reply(self, packet, server_ip=None, server_port=None, timeout=3.0):
        host, port = self._resolve_server_endpoint(server_ip, server_port)
        wire_packet = self._to_wire_payload(packet, force_zero_copy=True)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(wire_packet, (host, port))
            try:
                response, addr = sock.recvfrom(4096)
            except socket.timeout:
                return None
        try:
            self.protocol.classify_and_dispatch(response, addr)
        except Exception as e:
            os_log.err('MAIN', 'REPLY', e, {'host': host, 'port': port})
        return response

    def transmit(self, sensors, device_id=None, device_status='ONLINE', **kwargs):
        if self._is_id_missing():
            raise RuntimeError(f"[transmit] Device '{self.device_id}' has no assigned physical ID. Call ensure_id() first.")
        try:
            outbound_ts = int(float(kwargs.get('t', time.time())))
        except Exception:
            outbound_ts = int(time.time())
        if outbound_ts < int(getattr(self.protocol, 'min_valid_timestamp', 1000000)) and (not self.protocol.has_secure_dict(self.assigned_id)):
            synced_time = self.ensure_time()
            if synced_time:
                kwargs['t'] = synced_time
        target_name = device_id or self.device_id
        fact = self.standardizer.standardize(target_name, device_status, sensors, **kwargs)
        if self.db_manager:
            try:
                self.db_manager.export_fact(fact)
            except Exception as e:
                os_log.err('DB', 'EXPORT', e, {})
        compressed_str = self.engine.compress(fact)
        raw_input_str = f'{self.assigned_id};{compressed_str}'
        decomp = self.fusion._auto_decompose(raw_input_str)
        src_aid = decomp[3] if decomp else self.assigned_id
        ts_raw = self.fusion._decode_ts_token(decomp[0]) if decomp else 0
        reg = self.fusion._get_active_registry(src_aid)
        has_template = len(reg['data']['templates']) > 0
        strategy_label = self.protocol.get_strategy(src_aid, has_template)
        engine_strat = 'FULL' if strategy_label == 'FULL_PACKET' else 'DIFF'
        binary_packet = self.fusion.run_engine(raw_input_str, strategy=engine_strat)
        self.protocol.commit_success(src_aid)
        if binary_packet and self.protocol.normalize_data_cmd(binary_packet[0]) == CMD.DATA_FULL and (not self.protocol.is_secure_data_cmd(binary_packet[0])):
            self.protocol.note_local_plaintext_sent(src_aid, ts_raw)
        self._maybe_sync_registry(src_aid, reg)
        return (binary_packet, src_aid, strategy_label)

    def transmit_fast(self, sensors=None, device_id=None, device_status='ONLINE', **kwargs):
        # pycore keeps the same semantics as transmit; rscore can override with fused FFI.
        return self.transmit(sensors=sensors, device_id=device_id, device_status=device_status, **kwargs)

    def transmit_batch(self, batch_items, **kwargs):
        out = []
        for item in (batch_items or []):
            if isinstance(item, dict):
                merged = dict(kwargs)
                merged.update(item)
                out.append(self.transmit_fast(**merged))
            else:
                out.append(self.transmit_fast(sensors=item, **kwargs))
        return out

    def receive(self, raw_bytes):
        return self.fusion.decompress(raw_bytes)

    def receive_via_protocol(self, raw_bytes, addr=None):
        return self.protocol.classify_and_dispatch(raw_bytes, addr)

    def relay(self, packet):
        return self.fusion.relay(packet)

    def dispatch(self, packet, medium=None):
        target_medium = medium or self.config.get('OpenSynaptic_Setting', {}).get('default_medium', 'UDP')
        target_key = str(target_medium).strip().lower()
        driver = None
        if hasattr(self, 'transporter_manager'):
            driver = self.transporter_manager.get_driver(target_medium)
        if not driver:
            driver = self.active_transporters.get(target_key)
        if driver and hasattr(driver, 'send'):
            try:
                wire_packet = self._to_wire_payload(packet, config=self.config)
                result = driver.send(wire_packet, self.config)
                if not result:
                    os_log.err('MAIN', 'SEND_FAIL', f'Driver [{target_medium}] rejected send', {'len': payload_len(wire_packet)})
                return result
            except Exception as e:
                os_log.err('MAIN', 'PHYSICAL_ERR', e, {'medium': target_medium})
                return False
        os_log.err('MAIN', 'NO_DRIVER', f'No available driver: {target_medium}', {'requested': target_key, 'available': sorted(list(self.active_transporters.keys()))})
        return False
if __name__ == '__main__':
    os_node = OpenSynaptic()
    SERVER_IP = '192.168.1.100'
    SERVER_PORT = 8080
    os_node.ensure_id(server_ip=SERVER_IP, server_port=SERVER_PORT, device_meta={'type': 'sensor_node', 'hw': 'ESP32'})
    bin_packet, aid, strat = os_node.transmit(device_id='HUB_01', sensors=[['V1', 'OK', 621, 'Pa'], ['Vs1', 'OK', 621, 'Pa'], ['aV1', 'OK', 6321, 'Pa'], ['Vv1', 'OK', 6221, 'Pa'], ['VC1', 'OK', 611, 'Pa']])
    success = os_node.dispatch(bin_packet, medium='UDP')
    if success:
        os_log.log_with_const('info', LogMsg.SUCCESS_SEND, info=f'Sent {len(bin_packet)} bytes over UDP')
    else:
        os_log.log_with_const('error', LogMsg.FAILED_SEND, info='Send failed')
