"""RSCore Python compatibility layer.

When the Rust native library (os_rscore) is available the hot-path codec
is served by RsBase62Codec; all other symbols stay on pycore until their
Rust counterparts are ready.

Fallback chain:
  Rust DLL present  →  RsBase62Codec + CMD helpers from os_rscore
  Rust DLL absent   →  full pycore delegation (transparent, no exceptions)
"""
import os
import base64
import codecs
import struct

from opensynaptic.core.pycore.core import OpenSynaptic as _PyOpenSynaptic
from opensynaptic.core.pycore.handshake import CMD as _PyCMD
from opensynaptic.core.pycore.handshake import OSHandshakeManager as _PyOSHandshakeManager
from opensynaptic.core.pycore.solidity import OpenSynapticEngine as _PyOpenSynapticEngine
from opensynaptic.core.pycore.standardization import (
    OpenSynapticStandardizer as _PyOpenSynapticStandardizer,
)
from opensynaptic.core.pycore.transporter_manager import TransporterManager as _PyTransporterManager
from opensynaptic.core.pycore.unified_parser import OSVisualFusionEngine as _PyOSVisualFusionEngine

# Rust codec – imported lazily so missing DLL never breaks the import.
try:
    from opensynaptic.core.rscore.codec import RsBase62Codec as _RsBase62Codec
    from opensynaptic.core.rscore.codec import has_rs_native as _has_rs_native
    _RS_AVAILABLE = _has_rs_native()
except Exception:
    _RS_AVAILABLE = False
    _RsBase62Codec = None


# ─────────────────────────────────────────────────────────────────────────────
# Hybrid OpenSynapticEngine
# ─────────────────────────────────────────────────────────────────────────────

class OpenSynapticEngine(_PyOpenSynapticEngine):
    """Base62 compression engine – uses Rust codec when the DLL is present.

    If *os_rscore* is loaded the internal ``self.codec`` is replaced with
    ``RsBase62Codec``, keeping every other method identical to the pycore
    implementation.
    """

    def __init__(self, config_path=None):
        import math
        super().__init__(config_path=config_path)
        self._rs_solidity = None
        try:
            self._rs_compress_min_sensors = max(
                0,
                int(os.getenv('OPENSYNAPTIC_RS_COMPRESS_MIN_SENSORS', '4').strip() or '4'),
            )
        except Exception:
            self._rs_compress_min_sensors = 4
        if _RS_AVAILABLE and _RsBase62Codec is not None:
            # precision_val == 10**p (e.g. 10000 for p=4).  Recover p via log10.
            try:
                p = int(round(math.log10(self.precision_val))) if self.precision_val > 1 else 4
                self.codec = _RsBase62Codec(precision=p)
            except Exception:
                pass  # keep the C codec on any unexpected failure
            try:
                from opensynaptic.core.rscore.codec import RsSolidityCompressor, has_solidity_compressor
                if has_solidity_compressor():
                    self._rs_solidity = RsSolidityCompressor(
                        precision=p,
                        use_ms=bool(getattr(self, 'USE_MS', True)),
                        units_map=getattr(self, '_units_map', {}),
                        states_map=getattr(self, '_states_map', {}),
                    )
            except Exception:
                self._rs_solidity = None

    @staticmethod
    def _count_sensor_slots(data):
        i = 1
        count = 0
        while True:
            if not isinstance(data, dict) or data.get(f's{i}_id') is None:
                break
            count += 1
            i += 1
        return count

    def compress(self, data):
        """Compress *data* using the Rust solidity fast-path when available."""
        if self._rs_solidity is not None and self._count_sensor_slots(data) >= int(getattr(self, '_rs_compress_min_sensors', 4) or 0):
            try:
                return self._rs_solidity.compress(data)
            except Exception:
                pass
        return super().compress(data)


# ─────────────────────────────────────────────────────────────────────────────
# Remaining shims – identical surface area, no behaviour change yet
# ─────────────────────────────────────────────────────────────────────────────

class OpenSynaptic(_PyOpenSynaptic):
    """Orchestrator shim for the rscore plugin.

    Replaces both ``self.engine`` (Base62 codec) and ``self.fusion``
    (binary packet engine) with Rust-accelerated counterparts so the
    full transmit/receive pipeline exercises the Rust hot-paths.
    """

    def __init__(self, config_path=None):
        super().__init__(config_path=config_path)
        # ── Replace Base62 engine with Rust-backed version ───────────
        if _RS_AVAILABLE and _RsBase62Codec is not None:
            try:
                self.engine = OpenSynapticEngine(config_path)
            except Exception:
                pass  # keep pycore engine on any unexpected failure

        # ── Replace fusion engine with Rust CRC + header fast-path ───
        if _RS_AVAILABLE:
            try:
                rs_fusion = OSVisualFusionEngine(config_path)
                # Transfer local_id (set by parent's _sync_assigned_id_to_fusion)
                rs_fusion._set_local_id(self.fusion.local_id)
                # Share the RAM registry cache to avoid double disk reads
                rs_fusion._RAM_CACHE = self.fusion._RAM_CACHE
                rs_fusion._cache_lock = self.fusion._cache_lock
                self.fusion = rs_fusion
                # Re-wire protocol ↔ fusion so handshake state is consistent
                if getattr(self, 'protocol', None) is not None:
                    try:
                        self.fusion.protocol = self.protocol
                        self.protocol.parser = self.fusion
                    except Exception:
                        pass
            except Exception:
                pass  # keep pycore fusion on any unexpected failure


class OpenSynapticStandardizer(_PyOpenSynapticStandardizer):
    """UCUM standardizer – delegates to pycore until Rust parity is complete."""


class OSVisualFusionEngine(_PyOSVisualFusionEngine):
    """Binary packet engine – Rust fast-path header validation on decompress.

    When *os_rscore* is loaded ``decompress()`` first calls the Rust
    ``os_parse_header_min`` symbol to validate CRC16 and extract header
    metadata before delegating the full body decode to the pycore path.

    Benefits:
    * Corrupt packets are rejected in Rust before any Python struct work.
    * Falls back transparently to the pure-pycore path when the DLL is absent.
    """

    def __init__(self, config_path=None):
        super().__init__(config_path=config_path)
        self._rs_parse_header = None
        self._rs_crc8_fn = None
        self._rs_crc16_fn = None
        self._rs_auto_decompose = None
        self._rs_fusion_state = None
        self._rs_seeded_aids = set()
        try:
            self._rs_auto_decompose_min_bytes = max(
                0,
                int(os.getenv('OPENSYNAPTIC_RS_AUTO_DECOMPOSE_MIN_BYTES', '256').strip() or '256'),
            )
        except Exception:
            self._rs_auto_decompose_min_bytes = 256
        try:
            self._rs_fusion_min_values = max(
                0,
                int(os.getenv('OPENSYNAPTIC_RS_FUSION_STATE_MIN_VALUES', '4').strip() or '4'),
            )
        except Exception:
            self._rs_fusion_min_values = 4
        if _RS_AVAILABLE:
            try:
                from opensynaptic.core.rscore.codec import (
                    has_header_parser, parse_packet_header,
                    has_crc_helpers, rs_crc8, rs_crc16_ccitt,
                    has_auto_decompose, auto_decompose_input,
                    has_fusion_state, RsFusionState,
                )
                if has_header_parser():
                    self._rs_parse_header = parse_packet_header
                if has_crc_helpers():
                    self._rs_crc8_fn = rs_crc8
                    self._rs_crc16_fn = rs_crc16_ccitt
                if has_auto_decompose():
                    self._rs_auto_decompose = auto_decompose_input
                if has_fusion_state():
                    self._rs_fusion_state = RsFusionState()
            except Exception:
                pass  # DLL present but symbol absent – fall back silently

    def _raw_input_bytes(self, raw_input):
        if isinstance(raw_input, bytes):
            return raw_input
        if isinstance(raw_input, bytearray):
            return memoryview(raw_input)
        if isinstance(raw_input, memoryview):
            return raw_input
        return str(raw_input).encode('utf-8')

    def _decompose_with_rust(self, raw_input):
        if self._rs_auto_decompose is None:
            return None
        try:
            if isinstance(raw_input, str):
                raw_len = len(raw_input.encode('utf-8'))
            elif isinstance(raw_input, memoryview):
                raw_len = raw_input.nbytes
            else:
                raw_len = len(raw_input)
        except Exception:
            raw_len = 0
        if raw_len < int(getattr(self, '_rs_auto_decompose_min_bytes', 256) or 0):
            return None
        try:
            out = self._rs_auto_decompose(raw_input)
            if not out:
                return None
            ts_str, full_sig, raw_vals = out
            return (ts_str, full_sig, raw_vals, int(self.local_id), self._single_route_ids)
        except Exception:
            return None

    def _ensure_rs_fusion_seed(self, src_aid, reg):
        if self._rs_fusion_state is None:
            return False
        aid_key = int(src_aid)
        if aid_key in self._rs_seeded_aids:
            return True
        try:
            templates = reg.get('data', {}).get('templates', {}) if isinstance(reg, dict) else {}
            runtime_vals = reg.get('runtime_vals', {}) if isinstance(reg, dict) else {}
            self._rs_fusion_state.seed_aid(aid_key, templates, runtime_vals)
            self._rs_seeded_aids.add(aid_key)
            return True
        except Exception:
            return False

    def _refresh_rs_fusion_seed(self, src_aid, reg):
        if self._rs_fusion_state is None:
            return False
        try:
            self._rs_seeded_aids.discard(int(src_aid))
        except Exception:
            pass
        return self._ensure_rs_fusion_seed(src_aid, reg)

    @staticmethod
    def _sync_reg_from_native_result(reg, sig, vals_bin, native_result):
        if not isinstance(reg, dict) or not isinstance(native_result, dict):
            return
        tid = native_result.get('tid')
        if not tid:
            return
        if not isinstance(reg.get('data'), dict):
            reg['data'] = {'templates': {}}
        templates = reg['data'].setdefault('templates', {})
        sig_index = reg.setdefault('sig_index', {})
        runtime_vals = reg.setdefault('runtime_vals', {})
        dirty = False
        tpl = templates.get(tid)
        if not isinstance(tpl, dict) or tpl.get('sig') != sig:
            templates[tid] = {'sig': sig}
            dirty = True
        if sig_index.get(sig) != tid:
            sig_index[sig] = tid
            dirty = True
        if runtime_vals.get(tid) != list(vals_bin):
            runtime_vals[tid] = list(vals_bin)
            if native_result.get('runtime_changed') or native_result.get('new_template'):
                dirty = True
        if dirty:
            reg['dirty'] = True

    def run_engine(self, raw_input, strategy='DIFF'):
        """Encode packets using Rust decomposition + native fusion state when available."""
        decomp = self._decompose_with_rust(raw_input)
        if not decomp:
            return super().run_engine(raw_input, strategy=strategy)

        ts_str, sig, vals_bin, src_aid, route_ids = decomp
        reg = self._get_active_registry(src_aid)
        raw_input_bytes = self._raw_input_bytes(raw_input)

        if (
            self._rs_fusion_state is not None
            and route_ids is self._single_route_ids
            and len(vals_bin) >= int(getattr(self, '_rs_fusion_min_values', 4) or 0)
            and self._ensure_rs_fusion_seed(src_aid, reg)
        ):
            try:
                native = self._rs_fusion_state.apply(src_aid, strategy, sig, vals_bin)
                self._sync_reg_from_native_result(reg, sig, vals_bin, native)
                body_out = raw_input_bytes if native.get('use_raw_input_body') else native.get('body', b'')
                return self._finalize_bin(
                    native.get('cmd'),
                    native.get('tid'),
                    ts_str,
                    body_out,
                    route_ids,
                    src_aid=src_aid,
                )
            except Exception:
                pass

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
                tid = str(len(reg_data['templates']) + 1).zfill(2)
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

    def decompress(self, packet):
        """Decompress *packet* using the Rust header fast-path when available.

        If Rust detects a CRC16 mismatch the packet is rejected immediately
        without running the full Python decode.  Valid packets are handed to
        the pycore implementation which carries out template lookup and
        diff-reconstruction.
        """
        if self._rs_parse_header is not None:
            try:
                meta = self._rs_parse_header(packet)
                if meta is not None and not meta.get('crc16_ok'):
                    return {'error': 'CRC16 mismatch', '__packet_meta__': meta}
            except Exception:
                pass  # unexpected failure – fall through to pycore
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
            crc16_calc = self._rs_crc16_fn(packet_view[:-2]) if self._rs_crc16_fn is not None else None
            if crc16_calc is None:
                return super().decompress(packet)
            src_val = int.from_bytes(packet_view[tid_pos - 4:tid_pos], 'big') if r_cnt > 0 else 0
            meta = {'cmd': cmd, 'base_cmd': base_cmd, 'secure': secure, 'source_aid': src_val, 'crc16_ok': crc16_calc == crc16_recv}
            if crc16_calc != crc16_recv:
                return {'error': 'CRC16 mismatch', '__packet_meta__': meta}
            reg = self._get_active_registry(src_val)
            tid_str = str(packet_view[tid_pos]).zfill(2)
            ts_raw = packet_view[tid_pos + 1:tid_pos + 7]
            ts_enc = base64.urlsafe_b64encode(ts_raw).decode().rstrip('=')
            ts_raw_val = struct.unpack('>Q', b'\x00\x00' + ts_raw)[0]
            meta['timestamp_raw'] = ts_raw_val
            meta['tid'] = tid_str
            crc8_recv = packet_view[-3]
            wire_body = packet_view[tid_pos + 7:-3]
            if secure:
                protocol = getattr(self, 'protocol', None)
                key = protocol.get_session_key(src_val) if protocol and hasattr(protocol, 'get_session_key') else None
                if not key:
                    meta['crc8_ok'] = False
                    return {'error': f'Missing secure key for aid={src_val}', '__packet_meta__': meta}
                from opensynaptic.utils.security.security_core import xor_payload_into
                body_buf = bytearray(len(wire_body))
                xor_payload_into(wire_body, key, crc8_recv & 31, body_buf)
                body_bytes = memoryview(body_buf)
            else:
                body_bytes = wire_body
            crc8_calc = self._rs_crc8_fn(body_bytes) if self._rs_crc8_fn is not None else None
            if crc8_calc is None:
                return super().decompress(packet)
            meta['crc8_ok'] = crc8_calc == crc8_recv
            if crc8_calc != crc8_recv:
                return {'error': 'CRC8 mismatch', '__packet_meta__': meta}

            if (
                base_cmd in (127, 170)
                and self._rs_fusion_state is not None
                and self._ensure_rs_fusion_seed(src_val, reg)
            ):
                try:
                    raw_payload = self._rs_fusion_state.receive_apply(src_val, base_cmd, tid_str, ts_enc, bytes(body_bytes))
                    raw_str = codecs.decode(raw_payload, 'utf-8', errors='ignore')
                    if base_cmd == 170:
                        decomp = self._decompose_for_receive(raw_str)
                        if decomp:
                            sig, vals_bin = decomp
                            with reg['lock']:
                                reg_data = reg['data']
                                reg.setdefault('sig_index', {})[sig] = tid_str
                                if tid_str not in reg_data['templates'] or reg_data['templates'][tid_str].get('sig') != sig:
                                    reg_data['templates'][tid_str] = {'sig': sig}
                                reg.setdefault('runtime_vals', {})[tid_str] = list(vals_bin)
                                reg['dirty'] = True
                    from .solidity import OpenSynapticEngine
                    decoder = OpenSynapticEngine()
                    return self._attach_meta(decoder.decompress(raw_str), meta)
                except Exception:
                    pass

            result = super().decompress(packet)
            if base_cmd == 63 and isinstance(result, dict) and not result.get('error'):
                try:
                    self._refresh_rs_fusion_seed(src_val, reg)
                except Exception:
                    pass
            return result
        except Exception:
            return super().decompress(packet)

    def _finalize_bin(self, b, tid, ts_str, body_bytes, route_ids, src_aid=None):
        """Build binary wire frame using Rust CRC8 + CRC16 when available.

        Falls back to the pycore C-CRC path transparently when the Rust
        helpers are not loaded.  The XOR cipher for the secure path still
        uses the C ``xor_payload_into`` helper until a Rust equivalent is
        exported.
        """
        if self._rs_crc8_fn is None or self._rs_crc16_fn is None:
            return super()._finalize_bin(b, tid, ts_str, body_bytes, route_ids, src_aid=src_aid)

        from opensynaptic.utils.security.security_core import xor_payload_into

        # ── Route IDs → binary ───────────────────────────────────────────
        if route_ids is self._single_route_ids:
            r_bin = self._single_route_bin
            route_count = 1
        else:
            route_parts = []
            for rid in route_ids:
                if isinstance(rid, (bytes, bytearray)) and len(rid) == 4:
                    route_parts.append(rid if isinstance(rid, bytes) else bytes(rid))
                elif isinstance(rid, int):
                    route_parts.append(struct.pack('>I', rid))
                else:
                    s = str(rid)
                    if s.isdigit():
                        route_parts.append(struct.pack('>I', int(s)))
                    else:
                        route_parts.append(struct.pack('>I', self._decode_b62(s)))
            r_bin = b''.join(route_parts)
            route_count = len(route_ids)

        ts_raw = base64.urlsafe_b64decode(ts_str + '==')[:6]
        secure_enabled, secure_key = self._resolve_outbound_security(src_aid)
        wire_cmd = (
            getattr(getattr(self, 'protocol', None), 'secure_variant_cmd', lambda cmd: cmd)(b)
            if secure_enabled else b
        )

        body_view = memoryview(body_bytes)
        crc8_val = self._rs_crc8_fn(body_view)      # ← Rust CRC-8
        body_len = len(body_view)

        frame_len = 2 + len(r_bin) + 7 + body_len + 1 + 2
        frame = bytearray(frame_len)
        off = 0
        frame[off] = wire_cmd
        frame[off + 1] = route_count
        off += 2
        frame[off:off + len(r_bin)] = r_bin
        off += len(r_bin)
        frame[off] = int(tid)
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
        crc16_val = self._rs_crc16_fn(memoryview(frame)[:off])  # ← Rust CRC-16
        struct.pack_into('>H', frame, off, crc16_val)
        return bytes(frame)


class OSHandshakeManager(_PyOSHandshakeManager):
    """Handshake manager – uses Rust CMD helpers for hot-path routing methods.

    Three performance-sensitive methods are overridden to call the Rust
    ``os_cmd_*`` symbols instead of the Python dict lookups:

    * ``is_secure_data_cmd(cmd)``   – ``os_cmd_is_data`` + secure check
    * ``normalize_data_cmd(cmd)``   – ``os_cmd_normalize_data``
    * ``secure_variant_cmd(cmd)``   – ``os_cmd_secure_variant``

    All other state management (session keys, handshake sequences,
    ID allocation) is inherited unchanged from pycore.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rs_cmd_is_data = None
        self._rs_cmd_normalize = None
        self._rs_cmd_secure = None
        if _RS_AVAILABLE:
            try:
                from opensynaptic.core.rscore.codec import cmd_is_data, cmd_normalize_data, cmd_secure_variant
                self._rs_cmd_is_data = cmd_is_data
                self._rs_cmd_normalize = cmd_normalize_data
                self._rs_cmd_secure = cmd_secure_variant
            except Exception:
                pass

    def is_secure_data_cmd(self, cmd):
        """Return True when *cmd* is a secure-variant data command."""
        if self._rs_cmd_is_data is not None and self._rs_cmd_normalize is not None:
            try:
                return bool(self._rs_cmd_is_data(cmd)) and (self._rs_cmd_normalize(cmd) != cmd)
            except Exception:
                pass
        return super().is_secure_data_cmd(cmd)

    def normalize_data_cmd(self, cmd):
        """Return the base (plain) data command for *cmd*."""
        if self._rs_cmd_normalize is not None:
            try:
                return self._rs_cmd_normalize(cmd)
            except Exception:
                pass
        return super().normalize_data_cmd(cmd)

    def secure_variant_cmd(self, cmd):
        """Return the secure variant of *cmd*."""
        if self._rs_cmd_secure is not None:
            try:
                return self._rs_cmd_secure(cmd)
            except Exception:
                pass
        return super().secure_variant_cmd(cmd)


class TransporterManager(_PyTransporterManager):
    """Transport manager shim exposed by the rscore plugin."""


CMD = _PyCMD


def rs_native_available() -> bool:
    """Return True when the Rust DLL is loaded and active."""
    return _RS_AVAILABLE


__all__ = [
    'OpenSynaptic',
    'OpenSynapticStandardizer',
    'OpenSynapticEngine',
    'OSVisualFusionEngine',
    'OSHandshakeManager',
    'CMD',
    'TransporterManager',
    'rs_native_available',
]

