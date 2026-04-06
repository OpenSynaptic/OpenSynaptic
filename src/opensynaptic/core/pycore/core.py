# noinspection PyTypeChecker
import socket
import time
import threading
import copy
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
    get_user_config_path,
    get_project_config_path,
)
from opensynaptic.utils.buffer import to_wire_payload
try:
    from opensynaptic.services.db_engine import DatabaseManager
except Exception:
    DatabaseManager = None
from opensynaptic.utils.id_allocator import IDAllocator

class OpenSynaptic:
    MAX_UINT32 = 4294967295
    CONFIG_VERSION = 1

    def _deep_merge_missing(self, target, source):
        changed = False
        for key, value in (source or {}).items():
            if key not in target:
                target[key] = copy.deepcopy(value)
                changed = True
                continue
            if isinstance(target.get(key), dict) and isinstance(value, dict):
                if self._deep_merge_missing(target[key], value):
                    changed = True
        return changed

    # noinspection PyTypeChecker
    def _create_default_config(self):
        # 确保 parent[key] 始终是 dict 并返回其引用
        def _d(parent, key):
            v = parent.get(key)
            if not isinstance(v, dict):
                v = {}
                parent[key] = v
            return v

        template = read_json(get_project_config_path()) or {}
        if not isinstance(template, dict):
            template = {}
        if not template:
            template = {
                'device_id': 'DEMO_NODE',
                'assigned_id': 1,
                'OpenSynaptic_Setting': {'default_medium': 'UDP'},
                'Client_Core': {'server_host': '127.0.0.1', 'server_port': 8080},
                'Server_Core': {'host': '127.0.0.1', 'port': 8080, 'Start_ID': 1, 'End_ID': 4294967294},
                'engine_settings': {
                    'precision': 4,
                    'active_standardization': True,
                    'active_compression': True,
                    'active_collapse': True,
                    'zero_copy_transport': True,
                },
                'RESOURCES': {},
                'security_settings': {},
            }
        cfg = copy.deepcopy(template)
        cfg['config_version'] = int(cfg.get('config_version', self.CONFIG_VERSION) or self.CONFIG_VERSION)
        cfg.setdefault('first_run', True)
        cfg.setdefault('device_id', 'DEMO_NODE')
        if cfg.get('assigned_id') in (None, '', 0, '0', self.MAX_UINT32, str(self.MAX_UINT32)):
            cfg['assigned_id'] = 1

        _d(cfg, 'OpenSynaptic_Setting')['default_medium'] = 'UDP'

        client = _d(cfg, 'Client_Core')
        client['server_host'] = '127.0.0.1'
        client['server_port'] = 8080

        server = _d(cfg, 'Server_Core')
        server.setdefault('Start_ID', 1)
        server.setdefault('End_ID', 4294967294)
        server['host'] = '127.0.0.1'
        server['port'] = 8080

        resources = _d(cfg, 'RESOURCES')
        resources.setdefault('registry', 'data/device_registry/')

        app_status = _d(resources, 'application_status')
        for k in ('mqtt', 'matter', 'zigbee'):
            app_status.setdefault(k, False)

        transport_status = _d(resources, 'transport_status')
        for k, v in (('udp', True), ('tcp', False), ('quic', False), ('iwip', False), ('uip', False)):
            transport_status.setdefault(k, v)

        physical_status = _d(resources, 'physical_status')
        for k in ('uart', 'rs485', 'can', 'lora', 'bluetooth'):
            physical_status.setdefault(k, False)

        resources['transporters_status'] = {
            **{k: bool(v) for k, v in app_status.items()},
            **{k: bool(v) for k, v in transport_status.items()},
            **{k: bool(v) for k, v in physical_status.items()},
        }

        app_cfg = _d(resources, 'application_config')
        app_cfg.setdefault('mqtt', {'enabled': False})
        app_cfg.setdefault('matter', {'enabled': False, 'protocol': 'tcp', 'host': '127.0.0.1', 'port': 5540, 'timeout': 2.0})
        app_cfg.setdefault('zigbee', {'enabled': False, 'protocol': 'udp', 'host': '127.0.0.1', 'port': 6638, 'timeout': 2.0})

        _d(resources, 'transport_config').setdefault('udp', {'host': '127.0.0.1', 'port': 8080})

        physical_cfg = _d(resources, 'physical_config')
        for k in ('uart', 'rs485', 'can', 'lora'):
            physical_cfg.setdefault(k, {})
        physical_cfg.setdefault('bluetooth', {'enabled': False, 'protocol': 'udp', 'host': '127.0.0.1', 'port': 5454, 'timeout': 2.0})

        web_cfg = _d(_d(resources, 'service_plugins'), 'web_user')
        for k, v in (('enabled', True), ('mode', 'manual'), ('host', '127.0.0.1'), ('port', 8765), ('auto_start', False), ('auth_enabled', False)):
            web_cfg.setdefault(k, v)

        return cfg

    def _ensure_config_exists(self):
        cfg_path = Path(self.config_path)
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        if cfg_path.exists():
            return False
        legacy = Path(get_project_config_path())
        if legacy.exists() and legacy.resolve() != cfg_path.resolve():
            base = read_json(str(legacy)) or {}
            if not isinstance(base, dict):
                base = {}
            changed = self._deep_merge_missing(base, self._create_default_config())
            if changed:
                base['config_version'] = self.CONFIG_VERSION
            base.setdefault('migrated_from', str(legacy))
            write_json(str(cfg_path), base, indent=4)
            return True
        write_json(str(cfg_path), self._create_default_config(), indent=4)
        return True

    def _migrate_config_if_needed(self):
        current = int(self.config.get('config_version', 0) or 0)
        changed = False
        if current < self.CONFIG_VERSION:
            defaults = self._create_default_config()
            if self._deep_merge_missing(self.config, defaults):
                changed = True
            self.config['config_version'] = self.CONFIG_VERSION
            changed = True
        return changed

    def __init__(self, config_path=None):
        if config_path:
            self.config_path = str(Path(config_path).expanduser().resolve())
        else:
            self.config_path = str(Path(get_user_config_path()))
        self.base_dir = str(Path(self.config_path).resolve().parent)
        self._ensure_config_exists()
        self.config = read_json(self.config_path) or {}
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
        migrated_cfg = self._migrate_config_if_needed()
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
            device_role=str(self.settings.get('device_role', 'duplex') or 'duplex'),
        )
        self.protocol.min_valid_timestamp = int(self.security_settings.get('time_sync_threshold', self.protocol.min_valid_timestamp))
        self.protocol.id_allocator = self.id_allocator
        self.protocol.parser = self.fusion
        try:
            self.fusion.protocol = self.protocol
            # rx_only 角色跳过时间戳解码（constrained receiver 不关心时间）
            if getattr(self.protocol, 'device_role', 'duplex') == 'rx_only':
                self.fusion.skip_ts_decode = True
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
        if lease_changed or migrated_cfg:
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
        self.fusion._set_local_id(value)

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
        no_ts = bool(kwargs.pop('no_timestamp', False))
        if no_ts:
            # 无 RTC 设备：写入 sentinel TS=0，服务器会盖章并回复服务器时间
            kwargs['t'] = 0
        else:
            try:
                outbound_ts = int(float(kwargs.get('t', time.time())))
            except Exception:
                outbound_ts = int(time.time())
            if outbound_ts < int(getattr(self.protocol, 'min_valid_timestamp', 1000000)) and (not self.protocol.has_secure_dict(self.assigned_id)):
                # 优先使用 ID_ASSIGN 已损带的时间，无需额外一次 UDP 往返
                cached_srv_t = getattr(self.protocol, 'last_server_time', 0)
                if cached_srv_t > int(getattr(self.protocol, 'min_valid_timestamp', 1000000)):
                    kwargs['t'] = cached_srv_t
                else:
                    synced_time = self.ensure_time()
                    kwargs['t'] = synced_time if synced_time else int(time.time())
        target_name = device_id or self.device_id
        fact = self.standardizer.standardize(target_name, device_status, sensors, **kwargs)
        if self.db_manager:
            try:
                self.db_manager.export_fact(fact)
            except Exception as e:
                os_log.err('DB', 'EXPORT', e, {})
        compressed_str = self.engine.compress(fact)
        raw_input_str = f'{self.assigned_id};{compressed_str}'
        src_aid = int(self.assigned_id or 0)
        _t = fact.get('t', 0)
        ts_raw = (int(_t * 1000) if self.engine.USE_MS and _t < 10 ** 11 else int(_t)) if _t else 0
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

    def transmit_notimestamp(self, sensors=None, device_id=None, device_status='ONLINE', **kwargs):
        """RTC-less 设备专用入口。发挂 sentinel TS=0，服务器盖章并回复当前时间。
        收到回复后 last_server_time 更新，后续调用 transmit() 即可自动使用真实时间戳。"""
        return self.transmit(sensors=sensors, device_id=device_id, device_status=device_status, no_timestamp=True, **kwargs)

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
            settings = self.config.get('engine_settings', {}) if isinstance(self.config, dict) else {}
            retry_cfg = settings.get('network_retry', {}) if isinstance(settings.get('network_retry', {}), dict) else {}
            retry_enabled = bool(retry_cfg.get('enabled', True))
            max_retries = max(0, int(retry_cfg.get('max_retries', 2) or 0)) if retry_enabled else 0
            interval_s = max(0.0, float(retry_cfg.get('interval_seconds', 1.0) or 0.0))
            attempts = 1 + max_retries
            try:
                wire_packet = self._to_wire_payload(packet, config=self.config)
                for idx in range(attempts):
                    result = bool(driver.send(wire_packet, self.config))
                    if result:
                        return True
                    if idx < attempts - 1:
                        time.sleep(interval_s)
                os_log.err('MAIN', 'SEND_FAIL', f'Driver [{target_medium}] rejected send', {'len': payload_len(wire_packet), 'attempts': attempts})
                return False
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
