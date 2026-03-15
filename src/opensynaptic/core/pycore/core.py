import socket
import time
from pathlib import Path
from .standardization import OpenSynapticStandardizer
from .solidity import OpenSynapticEngine
from .unified_parser import OSVisualFusionEngine
from .handshake import OSHandshakeManager, CMD
from opensynaptic.utils.paths import read_json, write_json, ctx
from .transporter_manager import TransporterManager
from opensynaptic.services import ServiceManager
from opensynaptic.services.plugin_registry import sync_all_plugin_defaults
from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg
from opensynaptic.utils.c.native_loader import NativeLibraryUnavailable
from opensynaptic.utils.buffer import ensure_bytes, payload_len, zero_copy_enabled, as_readonly_view
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
        self.id_allocator = IDAllocator(base_dir=self.base_dir, start_id=start_id, end_id=end_id)
        registry_dir = getattr(ctx, 'registry_dir', None) or str(Path(self.base_dir) / 'data' / 'device_registry')
        Path(registry_dir).mkdir(parents=True, exist_ok=True)
        self.protocol = OSHandshakeManager(target_sync_count=3, registry_dir=registry_dir, expire_seconds=int(self.security_settings.get('secure_session_expire_seconds', 86400)))
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
        id_display = self.assigned_id if self.assigned_id else 'UNASSIGNED'
        os_log.log_with_const('info', LogMsg.READY, root=self.base_dir)
        if DatabaseManager:
            try:
                self.db_manager = DatabaseManager.from_opensynaptic_config(self.config)
                if self.db_manager:
                    self.service_manager.mount('db_engine', self.db_manager, config=self.config.get('storage', {}).get('sql', {}), mode='runtime')
                    self.service_manager.load('db_engine')
            except Exception as e:
                os_log.err('DB', 'INIT', e, {})

    def _sync_assigned_id_to_fusion(self):
        try:
            aid = self.assigned_id
            set_local_id = getattr(self.fusion, '_set_local_id', None)
            def _apply_local_id(value):
                if callable(set_local_id):
                    set_local_id(value)
                else:
                    self.fusion.local_id = value
                    self.fusion.local_id_str = str(value)
            if aid is None or aid == '' or aid == 'UNKNOWN' or (aid == self.MAX_UINT32) or (isinstance(aid, str) and aid.isdigit() and (int(aid) == self.MAX_UINT32)):
                _apply_local_id(0)
            elif isinstance(aid, int):
                _apply_local_id(aid)
            elif isinstance(aid, str) and aid.isdigit():
                _apply_local_id(int(aid))
            elif isinstance(aid, str) and aid:
                _apply_local_id(self.fusion._decode_b62(aid))
            else:
                _apply_local_id(0)
        except Exception as e:
            os_log.err('FUS', 'SYNC', e, {})
            if hasattr(self.fusion, '_set_local_id'):
                self.fusion._set_local_id(0)
            else:
                self.fusion.local_id = 0
                self.fusion.local_id_str = '0'

    def _is_id_missing(self):
        aid = self.assigned_id
        return aid is None or aid == 0 or aid == '' or (aid == '0') or (aid == 'UNKNOWN') or (aid == self.MAX_UINT32) or (isinstance(aid, str) and aid.isdigit() and (int(aid) == self.MAX_UINT32))

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

    def _load_json(self, path):
        return read_json(path)

    def ensure_id(self, server_ip, server_port, device_meta=None, timeout=5.0):
        if not self._is_id_missing():
            os_log.log_with_const('info', LogMsg.ID_ASSIGNED, addr=self.device_id, assigned=self.assigned_id)
            return True
        os_log.log_with_const('info', LogMsg.ID_REQUEST_TIMEOUT, timeout=0)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)

        def send_fn(data):
            sock.sendto(data, (server_ip, server_port))

        def recv_fn(timeout=1.0):
            sock.settimeout(timeout)
            try:
                data, _ = sock.recvfrom(4096)
                return data
            except socket.timeout:
                return None
        meta = device_meta or {}
        meta['device_id'] = self.device_id
        try:
            new_id = self.protocol.request_id_via_transport(transport_send_fn=send_fn, transport_recv_fn=recv_fn, device_meta=meta, timeout=timeout)
        finally:
            sock.close()
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
            server_time = self.protocol.request_time_via_transport(transport_send_fn=send_fn, transport_recv_fn=recv_fn, timeout=timeout)
        finally:
            sock.close()
        if server_time:
            self.protocol.note_server_time(server_time)
            os_log.log_with_const('info', LogMsg.TIME_SYNCED, server_time=server_time, host=host, port=port)
        return server_time

    def dispatch_with_reply(self, packet, server_ip=None, server_port=None, timeout=3.0):
        host, port = self._resolve_server_endpoint(server_ip, server_port)
        wire_packet = as_readonly_view(packet)
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
        if reg.get('dirty'):
            self.fusion._sync_to_disk(src_aid)
        return (binary_packet, src_aid, strategy_label)

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
                wire_packet = as_readonly_view(packet) if zero_copy_enabled(self.config) else ensure_bytes(packet)
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
