# rscore is glue-only; protocol logic lives in Rust FFI.
import inspect
import socket
import threading
import copy
import time
from collections import deque
from pathlib import Path

from opensynaptic.core.common.base import BaseOpenSynaptic
from opensynaptic.core.rscore._ffi_proxy import RsFFIProxyBase
from opensynaptic.services import ServiceManager
from opensynaptic.services.plugin_registry import sync_all_plugin_defaults, autoload_enabled_plugins
from opensynaptic.utils import read_json, write_json, os_log, payload_len, get_user_config_path, get_project_config_path
from opensynaptic.utils.buffer import to_wire_payload


class OpenSynaptic(BaseOpenSynaptic, RsFFIProxyBase):
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

    def _create_default_config(self):
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
                'RESOURCES': {},
                'security_settings': {},
            }
        cfg = copy.deepcopy(template)
        cfg['config_version'] = int(cfg.get('config_version', self.CONFIG_VERSION) or self.CONFIG_VERSION)
        cfg.setdefault('first_run', True)
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
            self._deep_merge_missing(base, self._create_default_config())
            base.setdefault('migrated_from', str(legacy))
            write_json(str(cfg_path), base, indent=4)
            return True
        write_json(str(cfg_path), self._create_default_config(), indent=4)
        return True

    def _migrate_config_if_needed(self):
        if not isinstance(self.config, dict):
            self.config = {}
        current = int(self.config.get('config_version', 0) or 0)
        if current >= self.CONFIG_VERSION:
            return False
        self._deep_merge_missing(self.config, self._create_default_config())
        self.config['config_version'] = self.CONFIG_VERSION
        return True

    def __init__(self, *args, **kwargs):
        config_path = kwargs.get('config_path')
        if config_path is None and args:
            config_path = args[0]
        if config_path:
            self.config_path = str(Path(config_path).expanduser().resolve())
        else:
            self.config_path = str(Path(get_user_config_path()))
        self.base_dir = str(Path(self.config_path).parent)
        self._ensure_config_exists()
        self.config = read_json(self.config_path) or {}

        self._init_ffi('RsOpenSynaptic', 'Rust node facade is unavailable', *args, **kwargs)
        ffi = self._require_ffi('Rust node facade is unavailable')
        self._ffi_ensure_id = ffi.ensure_id
        self._ffi_transmit = ffi.transmit
        self._ffi_dispatch = ffi.dispatch
        self._ffi_process_pipeline = getattr(ffi, 'process_pipeline', None)
        self._ffi_process_pipeline_batch = getattr(ffi, 'process_pipeline_batch', None)
        self._ffi_transmit_fast = getattr(ffi, 'transmit_fast', None)
        self._ffi_transmit_batch = getattr(ffi, 'transmit_batch', None)
        self._ffi_transmit_accepts_keywords = True
        try:
            sig = inspect.signature(self._ffi_transmit)
            self._ffi_transmit_accepts_keywords = ('sensors' in sig.parameters)
        except Exception:
            self._ffi_transmit_accepts_keywords = True

        from opensynaptic.core.rscore.handshake import OSHandshakeManager
        from opensynaptic.core.rscore.solidity import OpenSynapticEngine
        from opensynaptic.core.rscore.standardization import OpenSynapticStandardizer
        from opensynaptic.core.rscore.transporter_manager import TransporterManager
        from opensynaptic.core.rscore.unified_parser import OSVisualFusionEngine

        self.standardizer = OpenSynapticStandardizer(*args, **kwargs)
        self.engine = OpenSynapticEngine(*args, **kwargs)
        self.fusion = OSVisualFusionEngine(*args, **kwargs)
        self.protocol = OSHandshakeManager(*args, **kwargs)
        # Keep rscore runtime graph aligned with pycore: handshake needs parser,
        # and fusion can consult protocol for secure/command normalization helpers.
        try:
            self.protocol.parser = self.fusion
        except Exception:
            pass
        try:
            self.fusion.protocol = self.protocol
        except Exception:
            pass
        self.transporter_manager = TransporterManager(*args, **kwargs)
        self.service_manager = ServiceManager(config=self.config, mode='runtime')
        try:
            if sync_all_plugin_defaults(self.config):
                self._save_config()
        except Exception as exc:
            os_log.err('SVC', 'CFG_SYNC', exc, {})
        if self._migrate_config_if_needed():
            self._save_config()
        self.active_transporters = {}
        self.assigned_id = getattr(self._ffi, 'assigned_id', None)
        self.device_id = getattr(self._ffi, 'device_id', None)

        # Keep config-assigned id available for CLI/plugin flows.
        cfg_aid = self.config.get('assigned_id') if isinstance(self.config, dict) else None
        if self.assigned_id in (None, '') and cfg_aid not in (None, ''):
            self.assigned_id = cfg_aid
        if self.device_id in (None, ''):
            cfg_device = self.config.get('device_id') if isinstance(self.config, dict) else None
            self.device_id = cfg_device or 'UNKNOWN'

        # Keep FFI fallback state and fusion source-id aligned with config-assigned ID.
        try:
            if getattr(self, '_ffi', None) is not None:
                self._ffi.assigned_id = self.assigned_id
                self._ffi.device_id = self.device_id
        except Exception:
            pass
        self._sync_assigned_id_to_fusion()

        engine_cfg = self.config.get('engine_settings', {}) if isinstance(self.config, dict) else {}
        batch_cfg = engine_cfg.get('transmit_batch', {}) if isinstance(engine_cfg, dict) else {}
        if not isinstance(batch_cfg, dict):
            batch_cfg = {}
        self._tx_batch_enabled = bool(batch_cfg.get('enabled', True))
        self._tx_batch_max_items = max(1, int(batch_cfg.get('max_items', 16) or 16))
        self._tx_batch_window_s = max(0.0, float(batch_cfg.get('window_ms', 1.0) or 1.0) / 1000.0)
        self._tx_batch_wait_s = max(self._tx_batch_window_s * 4.0, 0.1)
        self._tx_batch_local = threading.local()

        adaptive_cfg = batch_cfg.get('adaptive', {}) if isinstance(batch_cfg.get('adaptive', {}), dict) else {}
        self._tx_adaptive_enabled = bool(adaptive_cfg.get('enabled', True))
        self._tx_adaptive_history_size = max(32, int(adaptive_cfg.get('history_size', 256) or 256))
        self._tx_adaptive_tune_every = max(8, int(adaptive_cfg.get('tune_every_batches', 32) or 32))
        self._tx_adaptive_target_tail_ms = max(0.1, float(adaptive_cfg.get('target_tail_ms', 30.0) or 30.0))
        self._tx_adaptive_window_ms_min = max(0.1, float(adaptive_cfg.get('window_ms_min', 0.5) or 0.5))
        self._tx_adaptive_window_ms_max = max(self._tx_adaptive_window_ms_min, float(adaptive_cfg.get('window_ms_max', 6.0) or 6.0))
        self._tx_adaptive_max_items_min = max(1, int(adaptive_cfg.get('max_items_min', 4) or 4))
        self._tx_adaptive_max_items_max = max(self._tx_adaptive_max_items_min, int(adaptive_cfg.get('max_items_max', 64) or 64))
        self._tx_adaptive_lock = threading.Lock()
        self._tx_adaptive_samples = deque(maxlen=self._tx_adaptive_history_size)
        self._tx_adaptive_batches_seen = 0
        self._last_dispatch_path = 'none'
        try:
            autoload_enabled_plugins(self, mode='runtime', auto_start_only=True)
        except Exception as exc:
            os_log.err('SVC', 'AUTOLOAD', exc, {})

    def _save_config(self):
        if not self.config_path:
            return
        try:
            write_json(self.config_path, self.config, indent=4)
        except Exception:
            return

    def _has_valid_assigned_id(self):
        aid = getattr(self, 'assigned_id', None)
        if aid in (None, '', 'UNKNOWN'):
            return False
        try:
            val = int(aid)
        except Exception:
            return False
        return 0 < val < self.MAX_UINT32

    def _is_id_missing(self):
        return not self._has_valid_assigned_id()

    def _resolve_server_endpoint(self, server_ip=None, server_port=None):
        client_cfg = self.config.get('Client_Core', {}) if isinstance(self.config, dict) else {}
        server_cfg = self.config.get('Server_Core', {}) if isinstance(self.config, dict) else {}
        host = server_ip or client_cfg.get('server_host') or server_cfg.get('host') or '127.0.0.1'
        port = int(server_port or client_cfg.get('server_port') or server_cfg.get('port') or 8080)
        return host, port

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

    def _persist_assigned_id(self, aid):
        try:
            val = int(aid)
        except Exception:
            return False
        if not (0 < val < self.MAX_UINT32):
            return False
        self.assigned_id = val
        if isinstance(self.config, dict):
            self.config['assigned_id'] = val
        self._sync_assigned_id_to_fusion()
        self._save_config()
        return True

    def ensure_id(self, server_ip=None, server_port=None, device_meta=None, *args, **kwargs):
        if self._has_valid_assigned_id():
            return True

        host, port = self._resolve_server_endpoint(server_ip, server_port)
        timeout = float(kwargs.get('timeout', 5.0) or 5.0)
        meta = dict(device_meta or {})
        meta.setdefault('device_id', self.device_id)

        out = None
        try:
            out = self._ffi_ensure_id(host, port, meta, *args, **kwargs)
        except Exception as exc:
            out = {'ok': False, 'error': str(exc)}

        if isinstance(out, dict):
            if bool(out.get('ok', False)):
                self._persist_assigned_id(out.get('assigned_id'))
                return out

        request_id_fn = getattr(self.protocol, 'request_id_via_transport', None)
        if callable(request_id_fn):
            def _request(send_fn, recv_fn):
                return request_id_fn(
                    transport_send_fn=send_fn,
                    transport_recv_fn=recv_fn,
                    device_meta=meta,
                    timeout=timeout,
                )

            try:
                new_id = self._run_udp_exchange(host, port, timeout, _request)
            except Exception:
                new_id = None

            if self._persist_assigned_id(new_id):
                return {'ok': True, 'assigned_id': int(self.assigned_id), 'source': 'protocol_fallback'}

        return out

    def ensure_time(self, server_ip=None, server_port=None, timeout=3.0):
        host, port = self._resolve_server_endpoint(server_ip, server_port)

        # Keep parity with pycore CLI API. Rust ABI for time sync may be unavailable.
        ffi_ensure_time = getattr(self._ffi, 'ensure_time', None)
        if callable(ffi_ensure_time):
            try:
                server_time = ffi_ensure_time(host, port, timeout)
                if server_time:
                    self.protocol.note_server_time(server_time)
                    return server_time
            except Exception:
                pass

        request_time_fn = getattr(self.protocol, 'request_time_via_transport', None)
        if callable(request_time_fn):
            def _request(send_fn, recv_fn):
                return request_time_fn(
                    transport_send_fn=send_fn,
                    transport_recv_fn=recv_fn,
                    timeout=timeout,
                )

            try:
                server_time = self._run_udp_exchange(host, port, timeout, _request)
            except Exception:
                server_time = None
            if server_time:
                self.protocol.note_server_time(server_time)
                return server_time

        return None

    def _transmit_fast_direct(self, sensors=None, device_id=None, device_status="ONLINE", **kwargs):
        if 'assigned_id' not in kwargs:
            kwargs['assigned_id'] = getattr(self, 'assigned_id', None)
        # Ensure FFI has the current assigned_id
        try:
            self._ffi.assigned_id = self.assigned_id
        except Exception:
            pass

        if callable(self._ffi_transmit_fast):
            result = self._ffi_transmit_fast(sensors=sensors, device_id=device_id, device_status=device_status, **kwargs)
        elif callable(self._ffi_process_pipeline):
            result = self._ffi_process_pipeline(sensors=sensors, device_id=device_id, device_status=device_status, **kwargs)
        elif self._ffi_transmit_accepts_keywords:
            result = self._ffi_transmit(sensors=sensors, device_id=device_id, device_status=device_status, **kwargs)
        else:
            result = self._ffi_transmit(sensors, device_id, device_status, **kwargs)

        # Fix aid to match assigned_id
        if isinstance(result, (tuple, list)) and len(result) == 3:
            packet, aid, strategy = result
            return packet, self.assigned_id, strategy
        return result

    def _transmit_batch_direct(self, batch_items, **kwargs):
        if callable(self._ffi_process_pipeline_batch):
            out = self._ffi_process_pipeline_batch(batch_items, return_metrics=False, **kwargs)
            if isinstance(out, dict):
                rows = out.get('results')
                if isinstance(rows, list):
                    return rows
            return out
        if callable(self._ffi_transmit_batch):
            return self._ffi_transmit_batch(batch_items, **kwargs)

        out = []
        for item in (batch_items or []):
            if isinstance(item, dict):
                merged = dict(kwargs)
                merged.update(item)
                out.append(self._transmit_fast_direct(**merged))
            else:
                out.append(self._transmit_fast_direct(item, **kwargs))
        return out

    @staticmethod
    def _percentile(values, ratio):
        if not values:
            return 0.0
        ordered = sorted(float(v or 0.0) for v in values)
        idx = int(round((len(ordered) - 1) * float(ratio)))
        if idx < 0:
            idx = 0
        if idx >= len(ordered):
            idx = len(ordered) - 1
        return ordered[idx]

    def _record_batch_metrics(self, batch_size):
        metrics = self.get_last_batch_metrics() if callable(getattr(self, 'get_last_batch_metrics', None)) else {}
        stage = metrics.get('stage_timing_ms', {}) if isinstance(metrics, dict) else {}
        sample = {
            'count': int(batch_size or metrics.get('count', 0) or 0),
            'compress_ms': float(stage.get('compress_ms', 0.0) or 0.0),
            'fuse_ms': float(stage.get('fuse_ms', 0.0) or 0.0),
        }
        with self._tx_adaptive_lock:
            self._tx_adaptive_samples.append(sample)
            self._tx_adaptive_batches_seen += 1

    def _maybe_adapt_batch_window(self):
        if not self._tx_adaptive_enabled:
            return
        with self._tx_adaptive_lock:
            if self._tx_adaptive_batches_seen < self._tx_adaptive_tune_every:
                return
            self._tx_adaptive_batches_seen = 0
            samples = list(self._tx_adaptive_samples)

        if len(samples) < 8:
            return

        fused_tail = self._percentile([s.get('fuse_ms', 0.0) + s.get('compress_ms', 0.0) for s in samples], 0.99)
        current_window_ms = self._tx_batch_window_s * 1000.0
        current_max_items = self._tx_batch_max_items

        if fused_tail > self._tx_adaptive_target_tail_ms:
            new_window_ms = max(self._tx_adaptive_window_ms_min, current_window_ms * 0.85)
            new_max_items = max(self._tx_adaptive_max_items_min, int(round(current_max_items * 0.9)))
        elif fused_tail < (self._tx_adaptive_target_tail_ms * 0.6):
            new_window_ms = min(self._tx_adaptive_window_ms_max, current_window_ms * 1.1)
            new_max_items = min(self._tx_adaptive_max_items_max, int(round(current_max_items * 1.1)))
        else:
            return

        self._tx_batch_window_s = max(0.0001, new_window_ms / 1000.0)
        self._tx_batch_max_items = max(1, int(new_max_items))
        self._tx_batch_wait_s = max(self._tx_batch_window_s * 4.0, 0.1)

    def _get_tx_local_state(self):
        state = getattr(self._tx_batch_local, 'state', None)
        if state is not None:
            return state
        state = {
            'lock': threading.Lock(),
            'queue': [],
            'timer': None,
        }
        self._tx_batch_local.state = state
        return state

    def _flush_tx_queue(self, state, force=False):
        with state['lock']:
            queue_size = len(state['queue'])
            if queue_size == 0:
                return
            if (not force) and queue_size < self._tx_batch_max_items:
                return
            entries = state['queue']
            state['queue'] = []
            timer = state['timer']
            state['timer'] = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass

        batch_items = [entry['item'] for entry in entries]
        try:
            results = self._transmit_batch_direct(batch_items)
        except Exception:
            results = []
        self._record_batch_metrics(len(batch_items))
        self._maybe_adapt_batch_window()
        if not isinstance(results, list):
            results = []

        for idx, entry in enumerate(entries):
            try:
                entry['result'] = results[idx] if idx < len(results) else self._transmit_fast_direct(**entry['item'])
            except Exception as e:
                entry['error'] = e
            finally:
                entry['event'].set()

    def _schedule_tx_flush(self, state):
        with state['lock']:
            if state['timer'] is not None:
                return
            timer = threading.Timer(self._tx_batch_window_s, self._flush_tx_queue, args=(state,), kwargs={'force': True})
            timer.daemon = True
            state['timer'] = timer
            timer.start()

    def _enqueue_transmit(self, item):
        state = self._get_tx_local_state()
        entry = {'item': item, 'event': threading.Event(), 'result': None, 'error': None}
        should_flush = False
        with state['lock']:
            state['queue'].append(entry)
            if len(state['queue']) >= self._tx_batch_max_items:
                should_flush = True
        if should_flush:
            self._flush_tx_queue(state, force=True)
        else:
            self._schedule_tx_flush(state)

        if (not entry['event'].wait(self._tx_batch_wait_s)):
            self._flush_tx_queue(state, force=True)
            entry['event'].wait(self._tx_batch_wait_s)
        if entry['error'] is not None:
            raise entry['error']
        if entry['result'] is not None:
            return entry['result']
        return self._transmit_fast_direct(**item)

    def transmit(self, sensors=None, device_id=None, device_status="ONLINE", **kwargs):
        return self.transmit_fast(sensors=sensors, device_id=device_id, device_status=device_status, **kwargs)

    def transmit_fast(self, sensors=None, device_id=None, device_status="ONLINE", **kwargs):
        if self._is_id_missing():
            raise RuntimeError(f"[transmit] Device '{self.device_id}' has no assigned physical ID. Call ensure_id() first.")
        item = {
            'sensors': sensors,
            'device_id': device_id,
            'device_status': device_status,
        }
        item.update(kwargs)
        if not self._tx_batch_enabled:
            return self._transmit_fast_direct(**item)
        return self._enqueue_transmit(item)

    def transmit_batch(self, batch_items, **kwargs):
        return self._transmit_batch_direct(batch_items, **kwargs)

    def get_last_batch_metrics(self):
        getter = getattr(self._ffi, 'get_last_batch_metrics', None)
        if callable(getter):
            return getter()
        return {'count': 0, 'stage_timing_ms': {'standardize_ms': 0.0, 'compress_ms': 0.0, 'fuse_ms': 0.0}, 'source': 'none'}

    def _to_wire_payload(self, payload, config=None, force_zero_copy=False):
        active_cfg = config if isinstance(config, dict) else self.config
        return to_wire_payload(payload, active_cfg, force_zero_copy=force_zero_copy)

    def get_last_dispatch_path(self):
        return str(getattr(self, '_last_dispatch_path', 'none') or 'none')


    def _dispatch_via_driver(self, wire_packet, medium):
        driver = None
        tm = getattr(self, 'transporter_manager', None)
        if tm is not None:
            get_driver = getattr(tm, 'get_driver', None)
            if callable(get_driver):
                driver = get_driver(medium)
        if not driver:
            key = str(medium or '').strip().lower()
            driver = (self.active_transporters or {}).get(key)
        if driver and hasattr(driver, 'send'):
            try:
                return bool(driver.send(wire_packet, self.config))
            except Exception as e:
                os_log.err('MAIN', 'PHYSICAL_ERR', e, {'medium': medium})
        return False

    def _dispatch_udp_fallback(self, wire_packet):
        host, port = self._resolve_server_endpoint()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.sendto(wire_packet, (host, port))
            return True
        except Exception as e:
            os_log.err('MAIN', 'UDP_FALLBACK', e, {'host': host, 'port': port, 'len': payload_len(wire_packet)})
            return False

    def dispatch(self, packet, medium="UDP", *args, **kwargs):
        target_medium = str(medium or 'UDP').strip()
        target_key = target_medium.lower()
        wire_packet = self._to_wire_payload(packet, config=self.config)
        self._last_dispatch_path = 'none'
        settings = self.config.get('engine_settings', {}) if isinstance(self.config, dict) else {}
        retry_cfg = settings.get('network_retry', {}) if isinstance(settings.get('network_retry', {}), dict) else {}
        retry_enabled = bool(retry_cfg.get('enabled', True))
        max_retries = max(0, int(retry_cfg.get('max_retries', 2) or 0)) if retry_enabled else 0
        interval_s = max(0.0, float(retry_cfg.get('interval_seconds', 1.0) or 0.0))
        attempts = 1 + max_retries

        for idx in range(attempts):
            try:
                out = self._ffi_dispatch(packet, target_medium, *args, **kwargs)
                if isinstance(out, dict):
                    if 'ok' in out and bool(out.get('ok')):
                        self._last_dispatch_path = 'ffi'
                        return True
                    if not bool(out.get('error')):
                        self._last_dispatch_path = 'ffi'
                        return True
                elif bool(out):
                    self._last_dispatch_path = 'ffi'
                    return True
            except Exception as e:
                os_log.err('MAIN', 'DISPATCH_FFI', e, {'medium': target_medium, 'attempt': idx + 1})

            if self._dispatch_via_driver(wire_packet, target_medium):
                self._last_dispatch_path = 'driver'
                return True

            if target_key == 'udp':
                ok = self._dispatch_udp_fallback(wire_packet)
                if ok:
                    self._last_dispatch_path = 'udp_fallback'
                    return True

            if idx < attempts - 1:
                time.sleep(interval_s)

        self._last_dispatch_path = 'failed'
        return False

    def receive(self, raw_bytes):
        return self.fusion.decompress(raw_bytes)

    def receive_via_protocol(self, raw_bytes, addr=None):
        return self.protocol.classify_and_dispatch(raw_bytes, addr)

    def relay(self, packet):
        return self.fusion.relay(packet)

    def _sync_assigned_id_to_fusion(self):
        aid = getattr(self, 'assigned_id', None)
        if aid in (None, ""):
            return None
        try:
            if getattr(self, '_ffi', None) is not None:
                self._ffi.assigned_id = int(aid)
        except Exception:
            pass
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

