import struct, base64
import threading
from pathlib import Path
from opensynaptic.utils.base62_codec import Base62Codec
from opensynaptic.utils.paths import read_json, write_json, get_registry_path, ctx
from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg
from opensynaptic.utils.security import crc8, crc16_ccitt, xor_payload

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
        registry_dir = getattr(ctx, 'registry_dir', None)
        if not registry_dir:
            registry_dir = str(Path(self.base_dir) / 'data' / 'Device_Registry')
        Path(registry_dir).mkdir(parents=True, exist_ok=True)
        self.root_dir = registry_dir
        self.local_id = 0
        self.local_id_str = '0'
        assigned = cfg.get('assigned_id', None)
        if assigned is None and config_path:
            try:
                explicit_cfg = read_json(str(Path(self.base_dir) / config_path))
                assigned = explicit_cfg.get('assigned_id') if explicit_cfg else None
            except Exception as e:
                os_log.err('FUS', 'CFG', e, {'path': config_path})
        if isinstance(assigned, int):
            self.local_id = int(assigned)
        elif isinstance(assigned, str) and assigned.isdigit():
            self.local_id = int(assigned)
        elif isinstance(assigned, str) and assigned:
            try:
                self.local_id = self._decode_b62(assigned)
            except Exception as e:
                os_log.err('FUS', 'B62_DECODE', e, {'val': assigned})
                self.local_id = 0
        self.local_id_str = str(self.local_id)

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

    def _get_active_registry(self, aid_str):
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
            if key in self._RAM_CACHE:
                return self._RAM_CACHE[key]
        f_path = get_registry_path(val)
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
        runtime_vals_by_tid = {}
        for tid, tpl in data.get('templates', {}).items():
            stored = tpl.get('last_vals_bin', [])
            runtime_vals_by_tid[tid] = [base64.b64decode(v) for v in stored]
        reg = {'data': data, 'path': f_path, 'dirty': False, 'lock': threading.RLock(), 'runtime_vals': runtime_vals_by_tid}
        with self._cache_lock:
            existing = self._RAM_CACHE.get(key)
            if existing:
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
                write_json(reg['path'], reg['data'], indent=4)
                reg['dirty'] = False

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
            work_str = raw_input
            if ';' in work_str:
                _, work_str = work_str.split(';', 1)
            head, payload = work_str.split('|', 1)
            h_base, ts_str = head.rsplit('.', 1)
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
            return (ts_str, full_sig, raw_vals, src_aid, [self.local_id])
        except Exception as e:
            os_log.err('FUS', 'DECOMPOSE', e, {'raw': raw_input})
            return None

    def run_engine(self, raw_input, strategy='DIFF'):
        decomp = self._auto_decompose(raw_input)
        if not decomp:
            return raw_input.encode()
        ts_str, sig, vals_bin, src_aid, route_ids = decomp
        reg = self._get_active_registry(src_aid)
        with reg['lock']:
            reg_data = reg['data']
            tid = next((k for k, v in reg_data['templates'].items() if v.get('sig') == sig), None)
            if not tid:
                tid = str(len(reg_data['templates']) + 1).zfill(2)
                reg_data['templates'][tid] = {'sig': sig}
                reg['dirty'] = True
            if not isinstance(reg.get('runtime_vals'), dict):
                reg['runtime_vals'] = {}
            tid_vals = reg['runtime_vals'].get(tid, [])
            if strategy == 'FULL':
                reg['runtime_vals'][tid] = list(vals_bin)
                reg_data['templates'][tid]['last_vals_bin'] = [base64.b64encode(v).decode() for v in vals_bin]
                reg['dirty'] = True
                return self._finalize_bin(63, tid, ts_str, raw_input.encode(), route_ids, src_aid=src_aid)
            if len(tid_vals) != len(vals_bin):
                return self.run_engine(raw_input, strategy='FULL')
            mask, diff_pay, changed = (0, b'', False)
            for i, v in enumerate(vals_bin):
                if v != tid_vals[i]:
                    mask |= 1 << i
                    diff_pay += struct.pack('B', len(v)) + v
                    tid_vals[i] = v
                    changed = True
            if not changed:
                return self._finalize_bin(127, tid, ts_str, b'', route_ids, src_aid=src_aid)
            reg['runtime_vals'][tid] = tid_vals
            reg_data['templates'][tid]['last_vals_bin'] = [base64.b64encode(v).decode() for v in tid_vals]
            reg['dirty'] = True
            mask_bytes = mask.to_bytes((len(vals_bin) + 7) // 8, 'big')
            return self._finalize_bin(170, tid, ts_str, mask_bytes + diff_pay, route_ids, src_aid=src_aid)

    def _finalize_bin(self, b, tid, ts_str, body_bytes, route_ids, src_aid=None):
        r_bin = b''
        for rid in route_ids:
            if isinstance(rid, (bytes, bytearray)) and len(rid) == 4:
                r_bin += bytes(rid)
                continue
            if isinstance(rid, int):
                r_bin += struct.pack('>I', rid)
                continue
            s = str(rid)
            if s.isdigit():
                r_bin += struct.pack('>I', int(s))
            else:
                val = self._decode_b62(s)
                r_bin += struct.pack('>I', val)
        ts_raw = base64.urlsafe_b64decode(ts_str + '==')[:6]
        secure_enabled, secure_key = self._resolve_outbound_security(src_aid)
        wire_cmd = getattr(getattr(self, 'protocol', None), 'secure_variant_cmd', lambda cmd: cmd)(b) if secure_enabled else b
        crc8_val = crc8(body_bytes)
        wire_body = xor_payload(body_bytes, secure_key, crc8_val & 31) if secure_enabled else body_bytes
        frame = struct.pack('>BB', wire_cmd, len(route_ids)) + r_bin + struct.pack('>B6s', int(tid), ts_raw) + wire_body + struct.pack('>B', crc8_val)
        crc16_val = crc16_ccitt(frame)
        return frame + struct.pack('>H', crc16_val)

    def decompress(self, packet):
        try:
            if not packet or len(packet) < 5:
                return {'error': 'Packet too short', '__packet_meta__': {'crc16_ok': False}}
            cmd = packet[0]
            r_cnt = packet[1]
            tid_pos = 2 + r_cnt * 4
            base_cmd = self._normalize_data_cmd(cmd)
            secure = self._is_secure_cmd(cmd)
            if len(packet) < tid_pos + 10:
                return {'error': 'Incomplete Binary Header', '__packet_meta__': {'crc16_ok': False, 'secure': secure}}
            crc16_recv = struct.unpack('>H', packet[-2:])[0]
            crc16_calc = crc16_ccitt(packet[:-2])
            src_val = int.from_bytes(packet[tid_pos - 4:tid_pos], 'big') if r_cnt > 0 else 0
            meta = {'cmd': cmd, 'base_cmd': base_cmd, 'secure': secure, 'source_aid': src_val, 'crc16_ok': crc16_calc == crc16_recv}
            if crc16_calc != crc16_recv:
                return {'error': 'CRC16 mismatch', '__packet_meta__': meta}
            reg = self._get_active_registry(src_val)
            tid_str = str(packet[tid_pos]).zfill(2)
            ts_raw = packet[tid_pos + 1:tid_pos + 7]
            ts_enc = base64.urlsafe_b64encode(ts_raw).decode().rstrip('=')
            ts_raw_val = struct.unpack('>Q', b'\x00\x00' + ts_raw)[0]
            meta['timestamp_raw'] = ts_raw_val
            meta['tid'] = tid_str
            crc8_recv = packet[-3]
            wire_body = packet[tid_pos + 7:-3]
            if secure:
                protocol = getattr(self, 'protocol', None)
                key = protocol.get_session_key(src_val) if protocol and hasattr(protocol, 'get_session_key') else None
                if not key:
                    meta['crc8_ok'] = False
                    return {'error': f'Missing secure key for aid={src_val}', '__packet_meta__': meta}
                body_bytes = xor_payload(wire_body, key, crc8_recv & 31)
            else:
                body_bytes = wire_body
            crc8_calc = crc8(body_bytes)
            meta['crc8_ok'] = crc8_calc == crc8_recv
            if crc8_calc != crc8_recv:
                return {'error': 'CRC8 mismatch', '__packet_meta__': meta}
            from opensynaptic.core.solidity import OpenSynapticEngine
            decoder = OpenSynapticEngine()
            with reg['lock']:
                reg_data = reg['data']
                if not isinstance(reg.get('runtime_vals'), dict):
                    reg['runtime_vals'] = {}
                if base_cmd == 63:
                    raw_str = body_bytes.decode('utf-8', errors='ignore')
                    decomp = self._decompose_for_receive(raw_str)
                    if decomp:
                        sig, vals_bin = decomp
                        if tid_str not in reg_data['templates'] or reg_data['templates'][tid_str].get('sig') != sig:
                            reg_data['templates'][tid_str] = {'sig': sig}
                        reg['runtime_vals'][tid_str] = list(vals_bin)
                        reg_data['templates'][tid_str]['last_vals_bin'] = [base64.b64encode(v).decode() for v in vals_bin]
                        reg['dirty'] = True
                        self._sync_to_disk(src_val)
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
                            tid_vals[i] = payload[off + 1:off + 1 + v_len]
                            off += 1 + v_len
                    reg['runtime_vals'][tid_str] = tid_vals
                    reg_data['templates'][tid_str]['last_vals_bin'] = [base64.b64encode(v).decode() for v in tid_vals]
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
            raw = packet
            if isinstance(packet, (bytes, bytearray)):
                try:
                    raw = packet.decode('utf-8', errors='ignore')
                except Exception:
                    return packet
            out = self.run_engine(raw)
            return out if isinstance(out, (bytes, bytearray)) else out.encode() if isinstance(out, str) else packet
        except Exception as e:
            os_log.err('FUS', 'RELAY', e, {'packet': packet})
            return packet
