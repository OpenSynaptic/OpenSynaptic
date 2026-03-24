from opensynaptic.core.common.base import BaseOSHandshakeManager, NativeLibraryUnavailable
from opensynaptic.core.rscore._ffi_proxy import RsFFIProxyBase
import struct
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

    def build_time_request(self):
        seq = self._next_seq()
        return struct.pack('>BH', CMD.TIME_REQUEST, seq)

    def _build_ack(self, seq=0):
        return struct.pack('>BH', CMD.HANDSHAKE_ACK, int(seq) & 0xFFFF)

    def _build_nack(self, seq=0, reason=''):
        return struct.pack('>BH', CMD.HANDSHAKE_NACK, int(seq) & 0xFFFF) + str(reason or '').encode('utf-8')

    def _build_pong(self, seq=0):
        return struct.pack('>BH', CMD.PONG, int(seq) & 0xFFFF)

    def _build_time_response(self, seq=0, server_time=0):
        return struct.pack('>BHQ', CMD.TIME_RESPONSE, int(seq) & 0xFFFF, int(server_time or 0))

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

