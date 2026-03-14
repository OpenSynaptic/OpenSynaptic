import json
import struct
import time
import threading
from typing import Optional, List
from opensynaptic.utils.paths import get_registry_path, read_json
from opensynaptic.utils.logger import os_log
from opensynaptic.utils.constants import LogMsg
from opensynaptic.utils.security import derive_session_key

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
    CTRL_CMDS = {ID_REQUEST, ID_ASSIGN, ID_POOL_REQ, ID_POOL_RES, HANDSHAKE_ACK, HANDSHAKE_NACK, PING, PONG, TIME_REQUEST, TIME_RESPONSE, SECURE_DICT_READY, SECURE_CHANNEL_ACK}
    BASE_DATA_CMD = {DATA_FULL_SEC: DATA_FULL, DATA_DIFF_SEC: DATA_DIFF, DATA_HEART_SEC: DATA_HEART}
    SECURE_DATA_CMD = {DATA_FULL: DATA_FULL_SEC, DATA_DIFF: DATA_DIFF_SEC, DATA_HEART: DATA_HEART_SEC}

class OSHandshakeManager:

    def __init__(self, target_sync_count=3, registry_dir=None, expire_seconds=86400):
        self.target_sync_count = target_sync_count
        self.registry_dir = registry_dir
        self.expire_seconds = expire_seconds
        self.registry_status = {}
        self.secure_sessions = {}
        self._lock = threading.Lock()
        self._seq_counter = 0
        self.id_allocator = None
        self.parser = None
        self.min_valid_timestamp = 1000000
        self.last_server_time = 0

    def _default_secure_session(self):
        return {'last': int(time.time()), 'peer_addr': None, 'first_plaintext_ts': None, 'pending_timestamp': None, 'pending_key': None, 'pending_key_hex': None, 'key': None, 'key_hex': None, 'dict_ready': False, 'decrypt_confirmed': False, 'state': 'INIT'}

    def _get_secure_session(self, aid=None, addr=None, create=True):
        key, _ = self._normalize_aid(aid)
        if not key:
            return None
        with self._lock:
            session = self.secure_sessions.get(key)
            if not session and create:
                session = self._default_secure_session()
                self.secure_sessions[key] = session
            if session:
                session['last'] = int(time.time())
                if addr:
                    session['peer_addr'] = str(addr)
            return session

    def get_session_key(self, aid):
        session = self._get_secure_session(aid, create=False)
        if not session:
            return None
        return session.get('key')

    def has_secure_dict(self, aid):
        session = self._get_secure_session(aid, create=False)
        return bool(session and session.get('dict_ready'))

    def should_encrypt_outbound(self, aid):
        session = self._get_secure_session(aid, create=False)
        return bool(session and session.get('dict_ready') and session.get('key'))

    def note_local_plaintext_sent(self, aid, timestamp_raw, addr=None):
        session = self._get_secure_session(aid, addr=addr, create=True)
        if not session or session.get('key') or session.get('pending_key'):
            return session
        key = derive_session_key(int(aid), int(timestamp_raw or 0))
        session['pending_timestamp'] = int(timestamp_raw or 0)
        session['pending_key'] = key
        session['pending_key_hex'] = key.hex()
        session['state'] = 'PLAINTEXT_SENT'
        return session

    def establish_remote_plaintext(self, aid, timestamp_raw, addr=None):
        session = self._get_secure_session(aid, addr=addr, create=True)
        if not session:
            return None
        if not session.get('key'):
            key = derive_session_key(int(aid), int(timestamp_raw or 0))
            session['key'] = key
            session['key_hex'] = key.hex()
            session['first_plaintext_ts'] = int(timestamp_raw or 0)
        session['dict_ready'] = True
        session['state'] = 'DICT_READY'
        return session

    def confirm_secure_dict(self, aid, timestamp_raw=None, addr=None):
        session = self._get_secure_session(aid, addr=addr, create=True)
        if not session:
            return False
        if not session.get('key'):
            if session.get('pending_key'):
                session['key'] = session['pending_key']
                session['key_hex'] = session.get('pending_key_hex')
                session['first_plaintext_ts'] = int(session.get('pending_timestamp') or 0)
            elif timestamp_raw is not None:
                key = derive_session_key(int(aid), int(timestamp_raw or 0))
                session['key'] = key
                session['key_hex'] = key.hex()
                session['first_plaintext_ts'] = int(timestamp_raw or 0)
        session['dict_ready'] = bool(session.get('key'))
        if session['dict_ready']:
            session['state'] = 'DICT_READY'
        return session['dict_ready']

    def mark_secure_channel(self, aid, addr=None):
        session = self._get_secure_session(aid, addr=addr, create=True)
        if not session:
            return None
        session['decrypt_confirmed'] = True
        session['state'] = 'SECURE'
        return session

    def note_server_time(self, server_time):
        try:
            self.last_server_time = int(server_time or 0)
        except Exception:
            self.last_server_time = 0

    def is_secure_data_cmd(self, cmd):
        return cmd in CMD.SECURE_DATA_CMDS

    def normalize_data_cmd(self, cmd):
        return CMD.BASE_DATA_CMD.get(cmd, cmd)

    def secure_variant_cmd(self, cmd):
        return CMD.SECURE_DATA_CMD.get(cmd, cmd)

    def classify_and_dispatch(self, packet, addr=None):
        if not packet or len(packet) < 1:
            return {'type': 'ERROR', 'cmd': 0, 'result': {'error': 'Empty packet'}, 'response': None}
        cmd = packet[0]
        if cmd in CMD.DATA_CMDS:
            result = None
            response = None
            if self.parser:
                result = self.parser.decompress(packet)
            else:
                result = {'error': 'No parser attached', 'raw_hex': packet.hex()}
            meta = result.get('__packet_meta__', {}) if isinstance(result, dict) else {}
            src_aid = meta.get('source_aid')
            ts_raw = meta.get('timestamp_raw')
            is_secure = bool(meta.get('secure'))
            if meta.get('crc16_ok') is False:
                return {'type': 'DATA', 'cmd': cmd, 'result': result, 'response': None}
            if src_aid is not None and (not result.get('error')):
                if not is_secure:
                    session = self._get_secure_session(src_aid, addr=addr, create=False)
                    if not (session and session.get('dict_ready')):
                        self.establish_remote_plaintext(src_aid, ts_raw, addr=addr)
                        response = self._build_secure_dict_ready(src_aid, ts_raw)
                elif is_secure:
                    session = self._get_secure_session(src_aid, addr=addr, create=False)
                    if not (session and session.get('decrypt_confirmed')):
                        self.mark_secure_channel(src_aid, addr=addr)
                        response = self._build_secure_channel_ack(src_aid)
            return {'type': 'DATA', 'cmd': cmd, 'result': result, 'response': response}
        if cmd in CMD.CTRL_CMDS:
            return self._handle_ctrl(cmd, packet, addr)
        return {'type': 'UNKNOWN', 'cmd': cmd, 'result': {'error': f'Unknown command 0x{cmd:02X}'}, 'response': self._build_nack(reason=f'Unknown CMD 0x{cmd:02X}')}

    def _handle_ctrl(self, cmd, packet, addr):
        if cmd == CMD.ID_REQUEST:
            return self._on_id_request(packet, addr)
        elif cmd == CMD.ID_ASSIGN:
            return self._on_id_assign(packet, addr)
        elif cmd == CMD.ID_POOL_REQ:
            return self._on_id_pool_request(packet, addr)
        elif cmd == CMD.ID_POOL_RES:
            return self._on_id_pool_response(packet, addr)
        elif cmd == CMD.HANDSHAKE_ACK:
            return self._on_ack(packet, addr)
        elif cmd == CMD.HANDSHAKE_NACK:
            return self._on_nack(packet, addr)
        elif cmd == CMD.PING:
            return self._on_ping(packet, addr)
        elif cmd == CMD.PONG:
            return self._on_pong(packet, addr)
        elif cmd == CMD.TIME_REQUEST:
            return self._on_time_request(packet, addr)
        elif cmd == CMD.TIME_RESPONSE:
            return self._on_time_response(packet, addr)
        elif cmd == CMD.SECURE_DICT_READY:
            return self._on_secure_dict_ready(packet, addr)
        elif cmd == CMD.SECURE_CHANNEL_ACK:
            return self._on_secure_channel_ack(packet, addr)
        return {'type': 'CTRL', 'cmd': cmd, 'result': {'error': 'Unhandled CTRL'}, 'response': None}

    def _on_id_request(self, packet, addr):
        seq = 0
        meta = {}
        try:
            if len(packet) >= 3:
                seq = struct.unpack('>H', packet[1:3])[0]
            if len(packet) > 3:
                meta_raw = packet[3:].decode('utf-8', errors='ignore')
                meta = json.loads(meta_raw) if meta_raw.strip() else {}
        except Exception as e:
            os_log.err('HND', 'PARSE', e, {'stage': 'id_request'})
        assigned_id = None
        if self.id_allocator:
            try:
                assigned_id = self.id_allocator.allocate_id(meta={'addr': str(addr) if addr else 'unknown', 'device_meta': meta, 'ts': int(time.time())})
            except RuntimeError:
                return {'type': 'CTRL', 'cmd': CMD.ID_REQUEST, 'result': {'status': 'REJECTED', 'reason': 'ID pool exhausted'}, 'response': self._build_nack(seq=seq, reason='ID_POOL_EXHAUSTED')}
        if assigned_id is not None:
            response = self._build_id_assign(seq, assigned_id)
            os_log.log_with_const('info', LogMsg.ID_ASSIGNED, addr=addr, assigned=assigned_id)
            return {'type': 'CTRL', 'cmd': CMD.ID_REQUEST, 'result': {'status': 'ASSIGNED', 'assigned_id': assigned_id, 'addr': addr}, 'response': response}
        else:
            return {'type': 'CTRL', 'cmd': CMD.ID_REQUEST, 'result': {'status': 'REJECTED', 'reason': 'No allocator'}, 'response': self._build_nack(seq=seq, reason='NO_ALLOCATOR')}

    def _on_id_assign(self, packet, addr):
        seq = 0
        assigned_id = None
        try:
            if len(packet) >= 3:
                seq = struct.unpack('>H', packet[1:3])[0]
            if len(packet) >= 7:
                assigned_id = struct.unpack('>I', packet[3:7])[0]
        except Exception as e:
            os_log.err('HND', 'PARSE', e, {'stage': 'id_assign'})
        if assigned_id is not None and assigned_id != 0:
            ack = self._build_ack(seq)
            os_log.log_with_const('info', LogMsg.ID_RECEIVED, assigned=assigned_id)
            return {'type': 'CTRL', 'cmd': CMD.ID_ASSIGN, 'result': {'status': 'RECEIVED', 'assigned_id': assigned_id}, 'response': ack}
        else:
            return {'type': 'CTRL', 'cmd': CMD.ID_ASSIGN, 'result': {'status': 'INVALID', 'raw': packet.hex()}, 'response': None}

    def _on_id_pool_request(self, packet, addr):
        seq = 0
        count = 1
        meta = {}
        try:
            if len(packet) >= 3:
                seq = struct.unpack('>H', packet[1:3])[0]
            if len(packet) >= 5:
                count = struct.unpack('>H', packet[3:5])[0]
            if len(packet) > 5:
                meta = json.loads(packet[5:].decode('utf-8', errors='ignore'))
        except Exception as e:
            os_log.err('HND', 'PARSE', e, {'stage': 'pool_req'})
        count = min(count, 256)
        pool = []
        if self.id_allocator:
            pool = self.id_allocator.allocate_pool(count, meta={'addr': str(addr) if addr else 'unknown', 'pool_request': True, 'ts': int(time.time())})
        if pool:
            response = self._build_id_pool_response(seq, pool)
            os_log.log_with_const('info', LogMsg.ID_POOL_ISSUED, addr=addr, count=len(pool))
            return {'type': 'CTRL', 'cmd': CMD.ID_POOL_REQ, 'result': {'status': 'POOL_ASSIGNED', 'pool': pool, 'count': len(pool)}, 'response': response}
        else:
            return {'type': 'CTRL', 'cmd': CMD.ID_POOL_REQ, 'result': {'status': 'REJECTED', 'reason': 'Cannot allocate pool'}, 'response': self._build_nack(seq=seq, reason='POOL_ALLOC_FAILED')}

    def _on_id_pool_response(self, packet, addr):
        seq = 0
        pool = []
        try:
            if len(packet) >= 3:
                seq = struct.unpack('>H', packet[1:3])[0]
            if len(packet) >= 5:
                count = struct.unpack('>H', packet[3:5])[0]
                offset = 5
                for _ in range(count):
                    if offset + 4 <= len(packet):
                        pool.append(struct.unpack('>I', packet[offset:offset + 4])[0])
                        offset += 4
        except Exception as e:
            os_log.err('HND', 'PARSE', e, {'stage': 'pool_res'})
        if pool:
            ack = self._build_ack(seq)
            os_log.log_with_const('info', LogMsg.ID_POOL_RECEIVED, count=len(pool), pool=pool)
            return {'type': 'CTRL', 'cmd': CMD.ID_POOL_RES, 'result': {'status': 'POOL_RECEIVED', 'pool': pool}, 'response': ack}
        return {'type': 'CTRL', 'cmd': CMD.ID_POOL_RES, 'result': {'status': 'EMPTY_POOL'}, 'response': None}

    def _on_ack(self, packet, addr):
        seq = struct.unpack('>H', packet[1:3])[0] if len(packet) >= 3 else 0
        return {'type': 'CTRL', 'cmd': CMD.HANDSHAKE_ACK, 'result': {'status': 'ACK_RECEIVED', 'seq': seq}, 'response': None}

    def _on_nack(self, packet, addr):
        seq = struct.unpack('>H', packet[1:3])[0] if len(packet) >= 3 else 0
        reason = ''
        if len(packet) > 3:
            reason = packet[3:].decode('utf-8', errors='ignore')
        return {'type': 'CTRL', 'cmd': CMD.HANDSHAKE_NACK, 'result': {'status': 'NACK_RECEIVED', 'seq': seq, 'reason': reason}, 'response': None}

    def _on_ping(self, packet, addr):
        seq = struct.unpack('>H', packet[1:3])[0] if len(packet) >= 3 else 0
        return {'type': 'CTRL', 'cmd': CMD.PING, 'result': {'status': 'PING', 'seq': seq}, 'response': self._build_pong(seq)}

    def _on_pong(self, packet, addr):
        seq = struct.unpack('>H', packet[1:3])[0] if len(packet) >= 3 else 0
        return {'type': 'CTRL', 'cmd': CMD.PONG, 'result': {'status': 'PONG', 'seq': seq}, 'response': None}

    def _on_time_request(self, packet, addr):
        seq = struct.unpack('>H', packet[1:3])[0] if len(packet) >= 3 else 0
        server_time = int(time.time())
        return {'type': 'CTRL', 'cmd': CMD.TIME_REQUEST, 'result': {'status': 'TIME_REQUEST', 'seq': seq, 'server_time': server_time}, 'response': self._build_time_response(seq, server_time)}

    def _on_time_response(self, packet, addr):
        seq = struct.unpack('>H', packet[1:3])[0] if len(packet) >= 3 else 0
        server_time = 0
        if len(packet) >= 11:
            server_time = struct.unpack('>Q', packet[3:11])[0]
        self.note_server_time(server_time)
        return {'type': 'CTRL', 'cmd': CMD.TIME_RESPONSE, 'result': {'status': 'TIME_RESPONSE', 'seq': seq, 'server_time': server_time}, 'response': None}

    def _on_secure_dict_ready(self, packet, addr):
        aid = 0
        timestamp_raw = None
        if len(packet) >= 5:
            aid = struct.unpack('>I', packet[1:5])[0]
        if len(packet) >= 13:
            timestamp_raw = struct.unpack('>Q', packet[5:13])[0]
        ready = self.confirm_secure_dict(aid, timestamp_raw=timestamp_raw, addr=addr)
        return {'type': 'CTRL', 'cmd': CMD.SECURE_DICT_READY, 'result': {'status': 'DICT_READY' if ready else 'DICT_PENDING', 'assigned_id': aid, 'timestamp_raw': timestamp_raw}, 'response': None}

    def _on_secure_channel_ack(self, packet, addr):
        aid = 0
        if len(packet) >= 5:
            aid = struct.unpack('>I', packet[1:5])[0]
        self.mark_secure_channel(aid, addr=addr)
        return {'type': 'CTRL', 'cmd': CMD.SECURE_CHANNEL_ACK, 'result': {'status': 'SECURE_CHANNEL_ACK', 'assigned_id': aid}, 'response': None}

    def _next_seq(self):
        with self._lock:
            self._seq_counter = self._seq_counter + 1 & 65535
            return self._seq_counter

    def build_id_request(self, device_meta=None):
        seq = self._next_seq()
        payload = json.dumps(device_meta or {}, ensure_ascii=False).encode('utf-8')
        return struct.pack('>BH', CMD.ID_REQUEST, seq) + payload

    def build_id_pool_request(self, count=10, meta=None):
        seq = self._next_seq()
        payload = json.dumps(meta or {}, ensure_ascii=False).encode('utf-8')
        return struct.pack('>BHH', CMD.ID_POOL_REQ, seq, count) + payload

    def build_ping(self):
        """構造 0x09 PING"""
        seq = self._next_seq()
        return struct.pack('>BH', CMD.PING, seq)

    def build_time_request(self):
        seq = self._next_seq()
        return struct.pack('>BH', CMD.TIME_REQUEST, seq)

    def _build_id_assign(self, seq, assigned_id):
        return struct.pack('>BHI', CMD.ID_ASSIGN, seq, assigned_id)

    def _build_id_pool_response(self, seq, pool):
        header = struct.pack('>BHH', CMD.ID_POOL_RES, seq, len(pool))
        body = b''
        for pid in pool:
            body += struct.pack('>I', int(pid))
        return header + body

    def _build_ack(self, seq=0):
        return struct.pack('>BH', CMD.HANDSHAKE_ACK, seq)

    def _build_nack(self, seq=0, reason=''):
        return struct.pack('>BH', CMD.HANDSHAKE_NACK, seq) + reason.encode('utf-8')

    def _build_pong(self, seq=0):
        return struct.pack('>BH', CMD.PONG, seq)

    def _build_time_response(self, seq=0, server_time=0):
        return struct.pack('>BHQ', CMD.TIME_RESPONSE, seq, int(server_time or 0))

    def _build_secure_dict_ready(self, assigned_id, timestamp_raw):
        return struct.pack('>BIQ', CMD.SECURE_DICT_READY, int(assigned_id or 0), int(timestamp_raw or 0))

    def _build_secure_channel_ack(self, assigned_id):
        return struct.pack('>BI', CMD.SECURE_CHANNEL_ACK, int(assigned_id or 0))

    def _normalize_aid(self, aid):
        if isinstance(aid, int):
            return (str(aid), aid)
        s = str(aid)
        if s.isdigit():
            return (s, int(s))
        return (s, None)

    def get_strategy(self, aid, has_template):
        self._cleanup_expired()
        key, int_val = self._normalize_aid(aid)
        with self._lock:
            if key not in self.registry_status:
                if self._check_persistence(aid) or has_template:
                    self.registry_status[key] = {'count': self.target_sync_count, 'last': int(time.time()), 'state': 'SYNCED'}
                else:
                    self.registry_status[key] = {'count': 0, 'last': int(time.time()), 'state': 'HANDSHAKING'}
            entry = self.registry_status[key]
        session = self._get_secure_session(aid, create=False)
        if has_template and session and session.get('dict_ready'):
            return 'DIFF_PACKET'
        if not has_template or entry['count'] < self.target_sync_count:
            return 'FULL_PACKET'
        return 'DIFF_PACKET'

    def commit_success(self, aid):
        key, _ = self._normalize_aid(aid)
        now = int(time.time())
        with self._lock:
            if key in self.registry_status:
                self.registry_status[key]['count'] += 1
                self.registry_status[key]['last'] = now
                if self.registry_status[key]['count'] >= self.target_sync_count:
                    self.registry_status[key]['state'] = 'SYNCED'
            else:
                self.registry_status[key] = {'count': 1, 'last': now, 'state': 'HANDSHAKING'}

    def _check_persistence(self, aid):
        key, int_val = self._normalize_aid(aid)
        if int_val is not None:
            path = get_registry_path(int_val)
            if path and read_json(path):
                return True
        path = get_registry_path(key)
        if path and read_json(path):
            return True
        return False

    def _cleanup_expired(self):
        now = int(time.time())
        with self._lock:
            expired = [k for k, v in self.registry_status.items() if now - v.get('last', 0) > self.expire_seconds]
            for k in expired:
                del self.registry_status[k]
            expired_sessions = [k for k, v in self.secure_sessions.items() if now - v.get('last', 0) > self.expire_seconds]
            for k in expired_sessions:
                del self.secure_sessions[k]

    def request_id_via_transport(self, transport_send_fn, transport_recv_fn, device_meta=None, timeout=5.0):
        req_packet = self.build_id_request(device_meta)
        try:
            transport_send_fn(req_packet)
        except Exception as e:
            os_log.err('ID 申請', '發送失敗', e)
            return None
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = transport_recv_fn(timeout=min(0.5, timeout - (time.time() - start)))
                if resp and len(resp) >= 1:
                    result = self.classify_and_dispatch(resp)
                    if result['cmd'] == CMD.ID_ASSIGN:
                        return result['result'].get('assigned_id')
                    elif result['cmd'] == CMD.HANDSHAKE_NACK:
                        os_log.err('ID 申請', '被拒絕', result['result'].get('reason'))
                        return None
            except Exception as e:
                os_log.err('ID 申請', '接收回覆失敗', e)
                time.sleep(0.05)
        os_log.err('ID 申請', f'超時 ({timeout}s)')
        return None

    def request_id_pool_via_transport(self, transport_send_fn, transport_recv_fn, count=10, meta=None, timeout=5.0):
        req_packet = self.build_id_pool_request(count, meta)
        try:
            transport_send_fn(req_packet)
        except Exception as e:
            os_log.err('ID 池申請', '發送失敗', e)
            return []
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = transport_recv_fn(timeout=min(0.5, timeout - (time.time() - start)))
                if resp and len(resp) >= 1:
                    result = self.classify_and_dispatch(resp)
                    if result['cmd'] == CMD.ID_POOL_RES:
                        return result['result'].get('pool', [])
                    elif result['cmd'] == CMD.HANDSHAKE_NACK:
                        return []
            except Exception as e:
                os_log.err('ID 池申請', '接收回覆失敗', e)
                time.sleep(0.05)
        return []

    def request_time_via_transport(self, transport_send_fn, transport_recv_fn, timeout=3.0):
        req_packet = self.build_time_request()
        try:
            transport_send_fn(req_packet)
        except Exception as e:
            os_log.err('TIME', 'SEND', e, {})
            return None
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = transport_recv_fn(timeout=min(0.5, timeout - (time.time() - start)))
                if resp and len(resp) >= 1:
                    result = self.classify_and_dispatch(resp)
                    if result['cmd'] == CMD.TIME_RESPONSE:
                        return result['result'].get('server_time')
                    if result['cmd'] == CMD.HANDSHAKE_NACK:
                        return None
            except Exception as e:
                os_log.err('TIME', 'RECV', e, {})
                time.sleep(0.05)
        return None
