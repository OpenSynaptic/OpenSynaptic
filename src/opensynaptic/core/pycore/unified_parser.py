import struct, base64, time
import threading
import codecs
from pathlib import Path
from opensynaptic.utils import (
    Base62Codec,
    read_json,
    write_json,
    get_registry_path,
    ctx,
    os_log,
    LogMsg,
    crc8,
    crc16_ccitt,
    xor_payload_into,
)

class OSVisualFusionEngine:

    def __init__(self, config_path='Config.json'):
        if config_path and Path(config_path).exists():
            self.base_dir = str(Path(config_path).resolve().parent)
            cfg = read_json(config_path) or {}
        else:
            self.base_dir = ctx.root
            cfg = ctx.config or {}
        self.CHARS = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
        self.codec = Base62Codec()
        self._RAM_CACHE = {}
        self._cache_lock = threading.RLock()
        cache_cfg = cfg.get('engine_settings', {}).get('cache_settings', {}) if isinstance(cfg.get('engine_settings', {}), dict) else {}
        fusion_cfg = cache_cfg.get('fusion_registry', {}) if isinstance(cache_cfg.get('fusion_registry', {}), dict) else {}
        self._cache_max_entries = max(64, int(fusion_cfg.get('max_entries', 1024) or 1024))
        self._cache_ttl_seconds = max(60, int(fusion_cfg.get('ttl_seconds', 3600) or 3600))
        self._cache_cleanup_interval = max(15, int(fusion_cfg.get('cleanup_interval_seconds', 120) or 120))
        self._cache_last_cleanup = 0.0
        engine_cfg = cfg.get('engine_settings', {}) if isinstance(cfg.get('engine_settings', {}), dict) else {}
        self._registry_sync_interval_seconds = max(0.0, float(engine_cfg.get('registry_sync_interval_seconds', 1.0) or 1.0))
        self._registry_sync_state_lock = threading.Lock()
        self._registry_last_sync = {}

        resources_cfg = cfg.get('RESOURCES', {}) if isinstance(cfg.get('RESOURCES', {}), dict) else {}
        registry_conf = resources_cfg.get('registry')
        registry_dir = None
        if registry_conf:
            rp = Path(str(registry_conf)).expanduser()
            registry_dir = str(rp if rp.is_absolute() else (Path(self.base_dir) / rp).resolve())
        if not registry_dir:
            registry_dir = getattr(ctx, 'registry_dir', None)
        if not registry_dir:
            registry_dir = str(Path(self.base_dir) / 'data' / 'device_registry')
        Path(registry_dir).mkdir(parents=True, exist_ok=True)
        self.root_dir = registry_dir
        self._set_local_id(0)
        assigned = cfg.get('assigned_id', None)
        if assigned is None and config_path:
            try:
                explicit_cfg = read_json(str(Path(self.base_dir) / config_path))
                assigned = explicit_cfg.get('assigned_id') if explicit_cfg else None
            except Exception as e:
                os_log.err('FUS', 'CFG', e, {'path': config_path})
        if isinstance(assigned, int):
            self._set_local_id(assigned)
        elif isinstance(assigned, str) and assigned.isdigit():
            self._set_local_id(int(assigned))
        elif isinstance(assigned, str) and assigned:
            try:
                self._set_local_id(self._decode_b62(assigned))
            except Exception as e:
                os_log.err('FUS', 'B62_DECODE', e, {'val': assigned})
                self._set_local_id(0)
        self._config_path = config_path
        self._decoder = None  # 延迟初始化，跨包复用避免重复构造
        self.skip_ts_decode = False  # rx_only 极端受限设备可设为 True，跳过时间戳解码
    def _set_local_id(self, local_id):
        val = int(local_id or 0)
        self.local_id = val
        self.local_id_str = str(val)
        self._single_route_ids = (val,)
        self._single_route_bin = struct.pack('>I', val)

    def _decode_ts_token(self, ts_str):
        try:
            ts_raw = base64.urlsafe_b64decode(str(ts_str) + '==')[:6]
            return struct.unpack('>Q', b'\x00\x00' + ts_raw)[0]
        except Exception as e:
            os_log.err('FUS', 'TS_DECODE', e, {'ts': ts_str})
            return 0

    def _is_secure_cmd(self, cmd):
        protocol = getattr(self, 'protocol', None)
        if protocol and hasattr(protocol, 'is_secure_data_cmd'):
            return protocol.is_secure_data_cmd(cmd)
        return cmd in {64, 171, 128}

    def _normalize_data_cmd(self, cmd):
        protocol = getattr(self, 'protocol', None)
        if protocol and hasattr(protocol, 'normalize_data_cmd'):
            return protocol.normalize_data_cmd(cmd)
        return {64: 63, 171: 170, 128: 127}.get(cmd, cmd)

    def _resolve_outbound_security(self, src_aid):
        protocol = getattr(self, 'protocol', None)
        if not protocol:
            return (False, None)
        try:
            if hasattr(protocol, 'should_encrypt_outbound') and protocol.should_encrypt_outbound(src_aid):
                return (True, protocol.get_session_key(src_aid))
        except Exception as e:
            os_log.err('FUS', 'SECURE_OUT', e, {'aid': src_aid})
        return (False, None)

    def _attach_meta(self, decoded, meta):
        if isinstance(decoded, dict):
            decoded['__packet_meta__'] = meta
        return decoded

    def _decode_b62(self, s):
        try:
            return int(self.codec.decode(str(s), use_precision=False))
        except Exception as e:
            os_log.err('FUS', 'B62_DECODE', e, {'val': s})
            return 0

    def _encode_b62(self, val):
        try:
            return self.codec.encode(int(val), use_precision=False)
        except Exception as e:
            os_log.err('FUS', 'B62_ENCODE', e, {'val': val})
            return '0'

    def _coerce_text(self, raw_input):
        if isinstance(raw_input, (bytes, bytearray, memoryview)):
            return codecs.decode(raw_input, 'utf-8', errors='ignore')
        return str(raw_input)

    def _coerce_bytes(self, raw_input):
        if isinstance(raw_input, (bytes, memoryview)):
            return raw_input
        if isinstance(raw_input, bytearray):
            return memoryview(raw_input)
        return str(raw_input).encode('utf-8')

    def _prune_cache_locked(self, now_ts=None):
        now_ts = float(now_ts if now_ts is not None else time.time())
        if (now_ts - self._cache_last_cleanup) < self._cache_cleanup_interval and len(self._RAM_CACHE) <= self._cache_max_entries:
            return
        expired = [
            key for key, reg in self._RAM_CACHE.items()
            if (now_ts - float(reg.get('last_seen', now_ts))) > self._cache_ttl_seconds
        ]
        for key in expired:
            self._RAM_CACHE.pop(key, None)
        if len(self._RAM_CACHE) > self._cache_max_entries:
            ordered = sorted(
                self._RAM_CACHE.items(),
                key=lambda kv: float(kv[1].get('last_seen', now_ts)),
            )
            drop_count = len(self._RAM_CACHE) - self._cache_max_entries
            for key, _ in ordered[:drop_count]:
                self._RAM_CACHE.pop(key, None)
        self._cache_last_cleanup = now_ts

    def _normalize_registry_data(self, data, key):
        repaired = False
        raw = data if isinstance(data, dict) else {}
        if not isinstance(data, dict):
            repaired = True
        normalized = dict(raw)
        normalized['aid'] = str(normalized.get('aid', key))
        templates = normalized.get('templates', {})
        if not isinstance(templates, dict):
            templates = {}
            repaired = True
        clean_templates = {}
        for tid, tpl in templates.items():
            if not isinstance(tpl, dict):
                repaired = True
                continue
            sig = tpl.get('sig')
            if not isinstance(sig, str) or not sig:
                repaired = True
                continue
            tid_key = str(tid).zfill(2)
            entry = dict(tpl)
            entry['sig'] = sig
            stored = entry.get('last_vals_bin')
            if stored is None:
                pass
            elif isinstance(stored, list):
                clean_stored = [v for v in stored if isinstance(v, str)]
                if len(clean_stored) != len(stored):
                    repaired = True
                if clean_stored:
                    entry['last_vals_bin'] = clean_stored
                else:
                    entry.pop('last_vals_bin', None)
            else:
                repaired = True
                entry.pop('last_vals_bin', None)
            clean_templates[tid_key] = entry
        normalized['templates'] = clean_templates
        return normalized, repaired

    def _get_active_registry(self, aid_str):
        now_ts = time.time()
        key = None
        if isinstance(aid_str, int):
            val = aid_str
            key = str(val)
        else:
            s = str(aid_str)
            if s.isdigit():
                val = int(s)
                key = s
            else:
                val = self._decode_b62(s)
                key = str(val)
        with self._cache_lock:
            reg = self._RAM_CACHE.get(key)
            if reg:
                reg['last_seen'] = now_ts
                return reg
        aid_str_z = str(int(val)).zfill(10)
        f_path = str(Path(self.root_dir) / aid_str_z[0:2] / aid_str_z[2:4] / f'{val}.json')
        p_dir = Path(f_path).parent
        p_dir.mkdir(parents=True, exist_ok=True)
        data = {'aid': key, 'templates': {}}
        f_p = Path(f_path)
        if f_p.exists():
            data = read_json(str(f_p))
        else:
            legacy_candidate = p_dir / f'{aid_str}.json'
            legacy_found = None
            if legacy_candidate.exists():
                legacy_found = legacy_candidate
            else:
                try:
                    for candidate in Path(self.root_dir).rglob(f'{aid_str}.json'):
                        legacy_found = candidate
                        break
                except Exception as e:
                    os_log.err('FUS', 'FS', e, {'root': self.root_dir, 'aid': aid_str})
            if legacy_found:
                data = read_json(str(legacy_found))
        data, repaired = self._normalize_registry_data(data, key)
        repaired_on_decode = False
        runtime_vals_by_tid = {}
        for tid, tpl in data.get('templates', {}).items():
            stored = tpl.get('last_vals_bin', [])
            decoded_vals = []
            for v in stored:
                try:
                    decoded_vals.append(base64.b64decode(v))
                except Exception:
                    repaired_on_decode = True
            runtime_vals_by_tid[tid] = decoded_vals
        sig_index = {}
        for tid, tpl in data.get('templates', {}).items():
            sig = tpl.get('sig')
            if sig:
                sig_index[sig] = tid
        reg = {
            'data': data,
            'path': f_path,
            'dirty': repaired or repaired_on_decode,
            'lock': threading.RLock(),
            'runtime_vals': runtime_vals_by_tid,
            'sig_index': sig_index,
            'last_seen': now_ts,
        }
        with self._cache_lock:
            self._prune_cache_locked(now_ts=now_ts)
            existing = self._RAM_CACHE.get(key)
            if existing:
                existing['last_seen'] = now_ts
                return existing
            self._RAM_CACHE[key] = reg
            return reg

    def _sync_to_disk(self, aid_str):
        key = str(aid_str)
        reg = self._RAM_CACHE.get(key)
        if not reg:
            return
        with reg['lock']:
            if reg['dirty']:
                templates = reg.get('data', {}).get('templates', {})
                runtime_vals = reg.get('runtime_vals', {}) if isinstance(reg.get('runtime_vals'), dict) else {}
                for tid, vals in runtime_vals.items():
                    tpl = templates.get(tid)
                    if isinstance(tpl, dict):
                        tpl['last_vals_bin'] = [base64.b64encode(v).decode() for v in vals]
                write_json(reg['path'], reg['data'], indent=4)
                reg['dirty'] = False

    def _maybe_sync_to_disk(self, aid_str, force=False):
        if force:
            self._sync_to_disk(aid_str)
            return
        key = str(aid_str)
        now = time.time()
        with self._registry_sync_state_lock:
            last = float(self._registry_last_sync.get(key, 0.0) or 0.0)
            if now - last < self._registry_sync_interval_seconds:
                return
            self._registry_last_sync[key] = now
        self._sync_to_disk(aid_str)

    def _decompose_for_receive(self, raw_input):
        try:
            work_str = raw_input
            if ';' in work_str:
                _, work_str = work_str.split(';', 1)
            head, payload = work_str.split('|', 1)
            h_base, ts_str = head.rsplit('.', 1)
            sig_segments = []
            vals_bin = []
            for seg in payload.split('|'):
                if not seg:
                    continue
                if '>' in seg and ':' in seg:
                    tag, content = seg.split('>', 1)
                    meta, val = content.rsplit(':', 1)
                    sig_segments.append(f'{tag}>\x01:\x01')
                    vals_bin.append(meta.encode('utf-8'))
                    vals_bin.append(val.encode('utf-8'))
                else:
                    sig_segments.append(seg)
            full_sig = f"{h_base}.{{TS}}|{'|'.join(sig_segments)}|"
            return (full_sig, vals_bin)
        except Exception as e:
            os_log.err('FUS', 'DECOMPOSE', e, {'raw': raw_input})
            return None

    def _auto_decompose(self, raw_input):
        try:
            work_str = self._coerce_text(raw_input)
            semi_idx = work_str.find(';')
            if semi_idx >= 0:
                work_str = work_str[semi_idx + 1:]
            pipe_idx = work_str.find('|')
            head = work_str[:pipe_idx]
            payload = work_str[pipe_idx + 1:]
            dot_idx = head.rfind('.')
            h_base = head[:dot_idx]
            ts_str = head[dot_idx + 1:]
            raw_vals = []
            sig_segments = []
            for seg in payload.split('|'):
                if not seg:
                    continue
                if '>' in seg and ':' in seg:
                    tag, content = seg.split('>', 1)
                    meta, val = content.rsplit(':', 1)
                    raw_vals.append(meta.encode('utf-8'))
                    raw_vals.append(val.encode('utf-8'))
                    sig_segments.append(f'{tag}>\x01:\x01')
                else:
                    sig_segments.append(seg)
            full_sig = f"{h_base}.{{TS}}|{'|'.join(sig_segments)}|"
            src_aid = int(self.local_id)
            return (ts_str, full_sig, raw_vals, src_aid, self._single_route_ids)
        except Exception as e:
            os_log.err('FUS', 'DECOMPOSE', e, {'raw': raw_input})
            return None

    def run_engine(self, raw_input, strategy='DIFF'):
        decomp = self._auto_decompose(raw_input)
        if not decomp:
            if isinstance(raw_input, bytes):
                return raw_input
            if isinstance(raw_input, (bytearray, memoryview)):
                return bytes(raw_input)
            return str(raw_input).encode('utf-8')
        ts_str, sig, vals_bin, src_aid, route_ids = decomp
        reg = self._get_active_registry(src_aid)
        raw_input_bytes = self._coerce_bytes(raw_input)
        if strategy == 'FULL':
            runtime_vals = reg.get('runtime_vals')
            sig_index = reg.get('sig_index')
            if isinstance(runtime_vals, dict) and isinstance(sig_index, dict):
                tid = sig_index.get(sig)
                tid_vals = runtime_vals.get(tid) if tid else None
                if tid_vals and len(tid_vals) == len(vals_bin) and (tid_vals == vals_bin):
                    return self._finalize_bin(63, tid, ts_str, raw_input_bytes, route_ids, src_aid=src_aid)
        cmd = None
        tid_out = None
        body_out = None
        with reg['lock']:
            reg_data = reg['data']
            sig_index = reg.setdefault('sig_index', {})
            tid = sig_index.get(sig)
            if not tid:
                _MAX_TIDS = 255  # TID is a 1-byte wire field (0x01–0xFF)
                if len(reg_data['templates']) < _MAX_TIDS:
                    tid = str(len(reg_data['templates']) + 1).zfill(2)
                else:
                    # FIFO eviction: reclaim the lowest-numbered TID slot so
                    # TID never overflows the single-byte frame field.  The
                    # next packet for this sig will be a FULL packet so the
                    # receiver re-learns the structure under the recycled TID.
                    _existing = sorted(reg_data['templates'], key=lambda t: int(t))
                    tid = _existing[0]
                    _old_sig = reg_data['templates'][tid].get('sig')
                    if _old_sig and sig_index.get(_old_sig) == tid:
                        del sig_index[_old_sig]
                    reg['runtime_vals'].pop(tid, None)
                    del reg_data['templates'][tid]
                reg_data['templates'][tid] = {'sig': sig}
                sig_index[sig] = tid
                reg['dirty'] = True
            if not isinstance(reg.get('runtime_vals'), dict):
                reg['runtime_vals'] = {}
            tid_vals = reg['runtime_vals'].get(tid, [])
            if strategy == 'FULL':
                if len(tid_vals) != len(vals_bin) or (tid_vals != vals_bin):
                    reg['runtime_vals'][tid] = list(vals_bin)
                    reg['dirty'] = True
                cmd = 63
                tid_out = tid
                body_out = raw_input_bytes
            elif len(tid_vals) != len(vals_bin):
                cmd = 63
                tid_out = tid
                reg['runtime_vals'][tid] = list(vals_bin)
                reg['dirty'] = True
                body_out = raw_input_bytes
            else:
                mask = 0
                diff_parts = []
                changed = False
                for i, v in enumerate(vals_bin):
                    if v != tid_vals[i]:
                        mask |= 1 << i
                        diff_parts.append(struct.pack('B', len(v)))
                        diff_parts.append(v)
                        tid_vals[i] = v
                        changed = True
                if not changed:
                    cmd = 127
                    tid_out = tid
                    body_out = b''
                else:
                    reg['runtime_vals'][tid] = tid_vals
                    reg['dirty'] = True
                    mask_bytes = mask.to_bytes((len(vals_bin) + 7) // 8, 'big')
                    cmd = 170
                    tid_out = tid
                    body_out = mask_bytes + b''.join(diff_parts)
        return self._finalize_bin(cmd, tid_out, ts_str, body_out, route_ids, src_aid=src_aid)

    def _finalize_bin(self, b, tid, ts_str, body_bytes, route_ids, src_aid=None):
        if route_ids is self._single_route_ids:
            r_bin = self._single_route_bin
            route_count = 1
        else:
            route_parts = []
            append_part = route_parts.append
            for rid in route_ids:
                if isinstance(rid, (bytes, bytearray)) and len(rid) == 4:
                    append_part(rid if isinstance(rid, bytes) else bytes(rid))
                    continue
                if isinstance(rid, int):
                    append_part(struct.pack('>I', rid))
                    continue
                s = str(rid)
                if s.isdigit():
                    append_part(struct.pack('>I', int(s)))
                else:
                    append_part(struct.pack('>I', self._decode_b62(s)))
            r_bin = b''.join(route_parts)
            route_count = len(route_ids)
        ts_raw = base64.urlsafe_b64decode(ts_str + '==')[:6]
        secure_enabled, secure_key = self._resolve_outbound_security(src_aid)
        wire_cmd = getattr(getattr(self, 'protocol', None), 'secure_variant_cmd', lambda cmd: cmd)(b) if secure_enabled else b
        body_view = memoryview(body_bytes)
        crc8_val = crc8(body_view)
        body_len = len(body_view)
        frame_len_no_crc16 = 2 + len(r_bin) + 7 + body_len + 1
        frame = bytearray(frame_len_no_crc16 + 2)
        off = 0
        frame[off] = wire_cmd
        frame[off + 1] = route_count
        off += 2
        frame[off:off + len(r_bin)] = r_bin
        off += len(r_bin)
        tid_byte = int(tid) & 0xFF  # guard: TID must fit in one byte (1-255)
        frame[off] = tid_byte
        frame[off + 1:off + 7] = ts_raw
        off += 7
        out_slice = memoryview(frame)[off:off + body_len]
        if secure_enabled:
            xor_payload_into(body_view, secure_key, crc8_val & 31, out_slice)
        else:
            out_slice[:] = body_view
        off += body_len
        frame[off] = crc8_val
        off += 1
        crc16_val = crc16_ccitt(memoryview(frame)[:off])
        struct.pack_into('>H', frame, off, crc16_val)
        return bytes(frame)

    def decompress(self, packet):
        try:
            if isinstance(packet, str):
                packet = packet.encode('utf-8')
            packet_view = memoryview(packet).cast('B')
            if len(packet_view) < 5:
                return {'error': 'Packet too short', '__packet_meta__': {'crc16_ok': False}}
            cmd = packet_view[0]
            r_cnt = packet_view[1]
            tid_pos = 2 + r_cnt * 4
            base_cmd = self._normalize_data_cmd(cmd)
            secure = self._is_secure_cmd(cmd)
            if len(packet_view) < tid_pos + 10:
                return {'error': 'Incomplete Binary Header', '__packet_meta__': {'crc16_ok': False, 'secure': secure}}
            crc16_recv = struct.unpack_from('>H', packet_view, len(packet_view) - 2)[0]
            crc16_calc = crc16_ccitt(packet_view[:-2])
            src_val = int.from_bytes(packet_view[tid_pos - 4:tid_pos], 'big') if r_cnt > 0 else 0
            meta = {'cmd': cmd, 'base_cmd': base_cmd, 'secure': secure, 'source_aid': src_val, 'crc16_ok': crc16_calc == crc16_recv}
            if crc16_calc != crc16_recv:
                return {'error': 'CRC16 mismatch', '__packet_meta__': meta}
            reg = self._get_active_registry(src_val)
            tid_str = str(packet_view[tid_pos]).zfill(2)
            # sentinel TS = 6 \x00: RTC-less 设备未提供时间戳，由服务器盖章
            _ts_raw_bytes = bytes(packet_view[tid_pos + 1:tid_pos + 7])
            if self.skip_ts_decode:
                # rx_only 极端受限设备：字节偏移不变，跳过解码节省 CPU
                ts_raw_val = 0
                ts_enc = 'AAAAAAAA'  # base64 of 6×\x00，下游 t=0
                meta['timestamp_raw'] = 0
                meta['server_stamped'] = False
            else:
                _server_stamped = (_ts_raw_bytes == b'\x00\x00\x00\x00\x00\x00')
                if _server_stamped:
                    ts_raw_val = int(time.time())
                    ts_enc = base64.urlsafe_b64encode(struct.pack('>Q', ts_raw_val)[2:]).decode().rstrip('=')
                else:
                    ts_raw_val = struct.unpack('>Q', b'\x00\x00' + _ts_raw_bytes)[0]
                    ts_enc = base64.urlsafe_b64encode(_ts_raw_bytes).decode().rstrip('=')
                meta['timestamp_raw'] = ts_raw_val
                meta['server_stamped'] = _server_stamped
            meta['tid'] = tid_str
            crc8_recv = packet_view[-3]
            wire_body = packet_view[tid_pos + 7:-3]
            if secure:
                protocol = getattr(self, 'protocol', None)
                key = protocol.get_session_key(src_val) if protocol and hasattr(protocol, 'get_session_key') else None
                if not key:
                    meta['crc8_ok'] = False
                    return {'error': f'Missing secure key for aid={src_val}', '__packet_meta__': meta}
                body_buf = bytearray(len(wire_body))
                xor_payload_into(wire_body, key, crc8_recv & 31, body_buf)
                body_bytes = memoryview(body_buf)
            else:
                body_bytes = wire_body
            crc8_calc = crc8(body_bytes)
            meta['crc8_ok'] = crc8_calc == crc8_recv
            if crc8_calc != crc8_recv:
                return {'error': 'CRC8 mismatch', '__packet_meta__': meta}
            if self._decoder is None:
                from .solidity import OpenSynapticEngine
                self._decoder = OpenSynapticEngine(self._config_path)
            decoder = self._decoder
            with reg['lock']:
                reg_data = reg['data']
                if not isinstance(reg.get('runtime_vals'), dict):
                    reg['runtime_vals'] = {}
                if base_cmd == 63:
                    raw_str = codecs.decode(body_bytes, 'utf-8', errors='ignore')
                    decomp = self._decompose_for_receive(raw_str)
                    if decomp:
                        sig, vals_bin = decomp
                        if tid_str not in reg_data['templates'] or reg_data['templates'][tid_str].get('sig') != sig:
                            reg_data['templates'][tid_str] = {'sig': sig}
                            reg.setdefault('sig_index', {})[sig] = tid_str
                        reg['runtime_vals'][tid_str] = list(vals_bin)
                        reg['dirty'] = True
                        self._maybe_sync_to_disk(src_val)
                        meta['template_learned'] = True
                        os_log.log_with_const('info', LogMsg.TEMPLATE_LEARNED, tid=tid_str, src=src_val, vars=len(vals_bin))
                    return self._attach_meta(decoder.decompress(raw_str), meta)
                if base_cmd == 127:
                    if tid_str not in reg_data['templates']:
                        return {'error': f'Template {tid_str} missing for 0x7F', '__packet_meta__': meta}
                    sig = reg_data['templates'][tid_str]['sig']
                    tid_vals = reg['runtime_vals'].get(tid_str, [])
                    if not tid_vals:
                        return {'error': f'No cached values for TID={tid_str}', '__packet_meta__': meta}
                    res_payload = sig.replace('{TS}', ts_enc)
                    for v in tid_vals:
                        res_payload = res_payload.replace('\x01', v.decode('utf-8', errors='ignore'), 1)
                    return self._attach_meta(decoder.decompress(res_payload), meta)
                if base_cmd == 170:
                    if tid_str not in reg_data['templates']:
                        return {'error': f'Template {tid_str} missing for 0xAA', '__packet_meta__': meta}
                    sig = reg_data['templates'][tid_str]['sig']
                    payload = body_bytes
                    tid_vals = reg['runtime_vals'].get(tid_str, [])
                    if not tid_vals:
                        return {'error': f'No cached values for TID={tid_str}', '__packet_meta__': meta}
                    mask_len = (len(tid_vals) + 7) // 8
                    mask = int.from_bytes(payload[:mask_len], 'big')
                    off = mask_len
                    for i in range(len(tid_vals)):
                        if mask >> i & 1:
                            v_len = payload[off]
                            tid_vals[i] = bytes(payload[off + 1:off + 1 + v_len])
                            off += 1 + v_len
                    reg['runtime_vals'][tid_str] = tid_vals
                    reg['dirty'] = True
                    res_payload = sig.replace('{TS}', ts_enc)
                    for v in tid_vals:
                        res_payload = res_payload.replace('\x01', v.decode('utf-8', errors='ignore'), 1)
                    return self._attach_meta(decoder.decompress(res_payload), meta)
                return {'error': f'Unknown Command {hex(cmd)}', '__packet_meta__': meta}
        except Exception as e:
            return os_log.err('FUS', 'DEC', e, {'packet': packet})

    def relay(self, packet):
        try:
            out = self.run_engine(packet)
            return out if isinstance(out, (bytes, bytearray)) else out.encode() if isinstance(out, str) else packet
        except Exception as e:
            os_log.err('FUS', 'RELAY', e, {'packet': packet})
            return packet
