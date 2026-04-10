from opensynaptic.core.common.base import BaseOSHandshakeManager, NativeLibraryUnavailable
from opensynaptic.core.rscore._ffi_proxy import RsFFIProxyBase
import json
import struct
import threading
import time


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
    CTRL_CMDS = {
        ID_REQUEST,
        ID_ASSIGN,
        ID_POOL_REQ,
        ID_POOL_RES,
        HANDSHAKE_ACK,
        HANDSHAKE_NACK,
        PING,
        PONG,
        TIME_REQUEST,
        TIME_RESPONSE,
        SECURE_DICT_READY,
        SECURE_CHANNEL_ACK,
    }
    BASE_DATA_CMD = {DATA_FULL_SEC: DATA_FULL, DATA_DIFF_SEC: DATA_DIFF, DATA_HEART_SEC: DATA_HEART}
    SECURE_DATA_CMD = {DATA_FULL: DATA_FULL_SEC, DATA_DIFF: DATA_DIFF_SEC, DATA_HEART: DATA_HEART_SEC}


class OSHandshakeManager(BaseOSHandshakeManager, RsFFIProxyBase):
    def __init__(self, *args, **kwargs):
        self._rs_cmd_is_data = None
        self._rs_cmd_normalize = None
        self._rs_cmd_secure = None
        self.id_allocator = None
        self.parser = None
        self.last_server_time = 0
        self._seq_counter = 0
        self._secure_sessions = {}
        self._ts_watermark = {}  # per-AID last-accepted timestamp for anti-replay
        self._ts_lock = threading.Lock()
        try:
            rs_codec = self._init_ffi('RsOSHandshakeManager', 'Rust handshake manager is unavailable', *args, **kwargs)
            self._rs_cmd_is_data = getattr(rs_codec, "cmd_is_data", None)
            self._rs_cmd_normalize = getattr(rs_codec, "cmd_normalize_data", None)
            self._rs_cmd_secure = getattr(rs_codec, "cmd_secure_variant", None)
        except NativeLibraryUnavailable:
            raise

    def negotiate(self, *args, **kwargs):
        return self._require_ffi('Rust native library not loaded').negotiate(*args, **kwargs)

    def is_secure_data_cmd(self, cmd):
        fn = self._rs_cmd_normalize
        if callable(fn):
            try:
                mapped = fn(int(cmd) & 0xFF)
                mapped_int = int(mapped() if callable(mapped) else mapped)
                return int(cmd) != mapped_int
            except Exception:
                pass
        return int(cmd) in CMD.SECURE_DATA_CMDS

    def normalize_data_cmd(self, cmd):
        fn = self._rs_cmd_normalize
        if callable(fn):
            try:
                mapped = fn(int(cmd) & 0xFF)
                return int(mapped() if callable(mapped) else mapped)
            except Exception:
                pass
        return CMD.BASE_DATA_CMD.get(int(cmd), int(cmd))

    def secure_variant_cmd(self, cmd):
        fn = self._rs_cmd_secure
        if callable(fn):
            try:
                mapped = fn(int(cmd) & 0xFF)
                return int(mapped() if callable(mapped) else mapped)
            except Exception:
                pass
        return CMD.SECURE_DATA_CMD.get(int(cmd), int(cmd))

    def classify_and_dispatch(self, packet, addr=None):
        if not packet or len(packet) < 1:
            return {'type': 'ERROR', 'cmd': 0, 'result': {'error': 'Empty packet'}, 'response': None}
        cmd = int(packet[0])

        if cmd in CMD.DATA_CMDS:
            parser = getattr(self, 'parser', None)
            if parser and callable(getattr(parser, 'decompress', None)):
                try:
                    result = parser.decompress(packet)
                except Exception as exc:
                    result = {'error': str(exc)}
            else:
                result = {'error': 'No parser attached'}
            return {'type': 'DATA', 'cmd': cmd, 'result': result, 'response': None}

        if cmd in CMD.CTRL_CMDS:
            return self._handle_ctrl(cmd, packet, addr)

        return {
            'type': 'UNKNOWN',
            'cmd': cmd,
            'result': {'error': f'Unknown command 0x{cmd:02X}'},
            'response': None,
        }

    def _handle_ctrl(self, cmd, packet, addr):
        if cmd == CMD.ID_REQUEST:
            return self._on_id_request(packet, addr)
        if cmd == CMD.HANDSHAKE_ACK:
            return self._on_ack(packet, addr)
        if cmd == CMD.HANDSHAKE_NACK:
            return self._on_nack(packet, addr)
        if cmd == CMD.PING:
            return self._on_ping(packet, addr)
        if cmd == CMD.PONG:
            return self._on_pong(packet, addr)
        if cmd == CMD.TIME_REQUEST:
            return self._on_time_request(packet, addr)
        if cmd == CMD.TIME_RESPONSE:
            return self._on_time_response(packet, addr)
        if cmd == CMD.ID_ASSIGN:
            return self._on_id_assign(packet, addr)
        return {
            'type': 'CTRL',
            'cmd': cmd,
            'result': {'status': 'UNHANDLED', 'reason': 'rscore standalone ctrl handler'},
            'response': self._build_nack(reason=f'UNHANDLED_CTRL_0x{cmd:02X}'),
        }

    def _seq_from_packet(self, packet):
        if packet and len(packet) >= 3:
            try:
                return int(struct.unpack('>H', packet[1:3])[0])
            except Exception:
                return 0
        return 0

    def _on_ack(self, packet, addr):
        seq = self._seq_from_packet(packet)
        return {'type': 'CTRL', 'cmd': CMD.HANDSHAKE_ACK, 'result': {'status': 'ACK_RECEIVED', 'seq': seq}, 'response': None}

    def _on_id_request(self, packet, addr):
        seq = self._seq_from_packet(packet)
        meta = {}
        if packet and len(packet) > 3:
            try:
                raw_meta = packet[3:].decode('utf-8', errors='ignore')
                if raw_meta.strip():
                    meta = json.loads(raw_meta)
            except Exception:
                meta = {}

        assigned_id = None
        allocator = getattr(self, 'id_allocator', None)
        if allocator is not None:
            try:
                assigned_id = allocator.allocate_id(
                    meta={
                        'addr': str(addr) if addr else 'unknown',
                        'device_meta': meta,
                        'device_id': meta.get('device_id') if isinstance(meta, dict) else None,
                        'ts': int(time.time()),
                    }
                )
            except Exception:
                assigned_id = None

        if assigned_id in (None, 0):
            parser = getattr(self, 'parser', None)
            fallback_id = getattr(parser, 'local_id', None) if parser is not None else None
            try:
                fallback_id = int(fallback_id)
            except Exception:
                fallback_id = None
            if isinstance(fallback_id, int) and 0 < fallback_id < 0xFFFFFFFF:
                assigned_id = fallback_id

        if assigned_id and int(assigned_id) > 0:
            aid = int(assigned_id)
            return {
                'type': 'CTRL',
                'cmd': CMD.ID_REQUEST,
                'result': {'status': 'ASSIGNED', 'assigned_id': aid, 'addr': addr},
                'response': self._build_id_assign(seq, aid),
            }

        return {
            'type': 'CTRL',
            'cmd': CMD.ID_REQUEST,
            'result': {'status': 'REJECTED', 'reason': 'NO_ALLOCATOR'},
            'response': self._build_nack(seq=seq, reason='NO_ALLOCATOR'),
        }

    def _on_nack(self, packet, addr):
        seq = self._seq_from_packet(packet)
        reason = packet[3:].decode('utf-8', errors='ignore') if packet and len(packet) > 3 else ''
        return {'type': 'CTRL', 'cmd': CMD.HANDSHAKE_NACK, 'result': {'status': 'NACK_RECEIVED', 'seq': seq, 'reason': reason}, 'response': None}

    def _on_ping(self, packet, addr):
        seq = self._seq_from_packet(packet)
        return {'type': 'CTRL', 'cmd': CMD.PING, 'result': {'status': 'PING', 'seq': seq}, 'response': self._build_pong(seq)}

    def _on_pong(self, packet, addr):
        seq = self._seq_from_packet(packet)
        return {'type': 'CTRL', 'cmd': CMD.PONG, 'result': {'status': 'PONG', 'seq': seq}, 'response': None}

    def _on_time_request(self, packet, addr):
        seq = self._seq_from_packet(packet)
        server_time = int(time.time())
        return {
            'type': 'CTRL',
            'cmd': CMD.TIME_REQUEST,
            'result': {'status': 'TIME_REQUEST', 'seq': seq, 'server_time': server_time},
            'response': self._build_time_response(seq, server_time),
        }

    def _on_time_response(self, packet, addr):
        seq = self._seq_from_packet(packet)
        server_time = 0
        if packet and len(packet) >= 11:
            try:
                server_time = int(struct.unpack('>Q', packet[3:11])[0])
            except Exception:
                server_time = 0
        self.note_server_time(server_time)
        return {'type': 'CTRL', 'cmd': CMD.TIME_RESPONSE, 'result': {'status': 'TIME_RESPONSE', 'seq': seq, 'server_time': server_time}, 'response': None}

    def _on_id_assign(self, packet, addr):
        seq = self._seq_from_packet(packet)
        assigned_id = 0
        if packet and len(packet) >= 7:
            try:
                assigned_id = int(struct.unpack('>I', packet[3:7])[0])
            except Exception:
                assigned_id = 0
        if assigned_id > 0:
            return {'type': 'CTRL', 'cmd': CMD.ID_ASSIGN, 'result': {'status': 'RECEIVED', 'assigned_id': assigned_id}, 'response': self._build_ack(seq)}
        return {'type': 'CTRL', 'cmd': CMD.ID_ASSIGN, 'result': {'status': 'INVALID', 'raw': packet.hex() if packet else ''}, 'response': None}

    def _next_seq(self):
        self._seq_counter = (int(self._seq_counter) + 1) & 0xFFFF
        return self._seq_counter

    def build_ping(self):
        seq = self._next_seq()
        return struct.pack('>BH', CMD.PING, seq)

    def build_id_request(self, device_meta=None):
        seq = self._next_seq()
        payload = json.dumps(device_meta or {}, ensure_ascii=False).encode('utf-8')
        return struct.pack('>BH', CMD.ID_REQUEST, seq) + payload

    def build_time_request(self):
        seq = self._next_seq()
        return struct.pack('>BH', CMD.TIME_REQUEST, seq)

    def _build_id_assign(self, seq=0, assigned_id=0):
        return struct.pack('>BHI', CMD.ID_ASSIGN, int(seq) & 0xFFFF, int(assigned_id or 0))

    def _build_ack(self, seq=0):
        return struct.pack('>BH', CMD.HANDSHAKE_ACK, int(seq) & 0xFFFF)

    def _build_nack(self, seq=0, reason=''):
        return struct.pack('>BH', CMD.HANDSHAKE_NACK, int(seq) & 0xFFFF) + str(reason or '').encode('utf-8')

    def _build_pong(self, seq=0):
        return struct.pack('>BH', CMD.PONG, int(seq) & 0xFFFF)

    def _build_time_response(self, seq=0, server_time=0):
        return struct.pack('>BHQ', CMD.TIME_RESPONSE, int(seq) & 0xFFFF, int(server_time or 0))

    def request_id_via_transport(self, transport_send_fn, transport_recv_fn, device_meta=None, timeout=5.0):
        req_packet = self.build_id_request(device_meta)
        try:
            transport_send_fn(req_packet)
        except Exception:
            return None

        start = time.time()
        while time.time() - start < timeout:
            wait_s = min(0.5, max(0.0, timeout - (time.time() - start)))
            try:
                resp = transport_recv_fn(timeout=wait_s)
                if resp and len(resp) >= 1:
                    result = self.classify_and_dispatch(resp)
                    if result.get('cmd') == CMD.ID_ASSIGN:
                        return (result.get('result') or {}).get('assigned_id')
                    if result.get('cmd') == CMD.HANDSHAKE_NACK:
                        return None
            except Exception:
                time.sleep(0.05)
        return None

    def request_time_via_transport(self, transport_send_fn, transport_recv_fn, timeout=3.0):
        req_packet = self.build_time_request()
        try:
            transport_send_fn(req_packet)
        except Exception:
            return None

        start = time.time()
        while time.time() - start < timeout:
            wait_s = min(0.5, max(0.0, timeout - (time.time() - start)))
            try:
                resp = transport_recv_fn(timeout=wait_s)
                if resp and len(resp) >= 1:
                    result = self.classify_and_dispatch(resp)
                    if result.get('cmd') == CMD.TIME_RESPONSE:
                        return (result.get('result') or {}).get('server_time')
                    if result.get('cmd') == CMD.HANDSHAKE_NACK:
                        return None
            except Exception:
                time.sleep(0.05)
        return None

    def get_session_key(self, aid):
        session = self._secure_sessions.get(str(aid), {})
        key = session.get('key') if isinstance(session, dict) else None
        return key if isinstance(key, (bytes, bytearray)) else None

    def should_encrypt_outbound(self, aid):
        session = self._secure_sessions.get(str(aid), {})
        if isinstance(session, dict) and session.get('dict_ready') and session.get('key'):
            return True
        return False

    def note_local_plaintext_sent(self, aid, ts_raw):
        key = str(aid)
        session = self._secure_sessions.get(key)
        if isinstance(session, dict):
            session = dict(session)
        else:
            session = {'state': 'PLAINTEXT', 'dict_ready': False}
        session['first_plaintext_ts'] = int(ts_raw or 0)
        session['last_plaintext_ts'] = int(ts_raw or 0)
        session['last_sent_at'] = int(time.time())
        self._secure_sessions[key] = session
        return session

    def note_server_time(self, server_time):
        try:
            self.last_server_time = int(server_time or 0)
        except Exception:
            self.last_server_time = 0
        return self.last_server_time

    def check_timestamp(self, aid, ts):
        """Evaluate ts against the per-AID last-accepted-timestamp watermark.

        Returns 'ACCEPT', 'REPLAY', or 'OUT_OF_ORDER'.
        The first call for a given AID is always ACCEPT and initialises the watermark.
        Strictly increasing timestamps advance the watermark and return ACCEPT.
        Equal timestamps return REPLAY; decreasing timestamps return OUT_OF_ORDER.
        """
        key = str(aid) if aid is not None else ''
        if not key:
            return 'ACCEPT'
        ts_int = int(ts or 0)
        with self._ts_lock:
            last = self._ts_watermark.get(key)
            if last is None:
                self._ts_watermark[key] = ts_int
                return 'ACCEPT'
            if ts_int > last:
                self._ts_watermark[key] = ts_int
                return 'ACCEPT'
            if ts_int == last:
                return 'REPLAY'
            return 'OUT_OF_ORDER'

