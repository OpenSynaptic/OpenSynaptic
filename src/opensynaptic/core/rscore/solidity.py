# rscore engine facade: strict Rust-first compressor/decompressor bridge.
import base64
import struct
from pathlib import Path

from opensynaptic.core.common.base import BaseOpenSynapticEngine, NativeLibraryUnavailable
from opensynaptic.utils import read_json, ctx


class OpenSynapticEngine(BaseOpenSynapticEngine):
    def __init__(self, config_path=None):
        self._ffi = None
        self._rs_solidity = None
        self._symbols = {}
        self._units_map = {}
        self._states_map = {}
        self.REV_UNIT = {}
        self.REV_STATE = {}

        try:
            from opensynaptic.core.rscore.codec import RsBase62Codec, RsSolidityCompressor, has_rs_native

            if not has_rs_native():
                raise NativeLibraryUnavailable("Rust native library not loaded")

            self._ffi = RsBase62Codec()
            self.codec = self._ffi
            self._load_symbols(config_path)

            precision = len(str(int(getattr(self._ffi, "precision_val", 10000)))) - 1
            if precision < 1 or precision > 18:
                precision = 4

            self._rs_solidity = RsSolidityCompressor(
                precision=precision,
                use_ms=True,
                units_map=self._units_map,
                states_map=self._states_map,
            )
        except Exception as e:
            self._ffi = None
            self._rs_solidity = None
            raise NativeLibraryUnavailable("Rust solidity path is unavailable") from e

    def _load_symbols(self, config_path=None):
        base_dir = Path(ctx.root)
        cfg = ctx.config or {}
        if config_path:
            cfg_path = Path(config_path)
            if cfg_path.exists():
                cfg = read_json(str(cfg_path)) or {}
                base_dir = cfg_path.resolve().parent
        res = cfg.get('RESOURCES', {}) if isinstance(cfg, dict) else {}
        sym_ref = res.get('prefixes') or res.get('symbols')
        candidates = []
        if sym_ref:
            candidates.append(base_dir / str(sym_ref))
        candidates.extend(
            [
                base_dir / 'libraries' / 'OS_Symbols.json',
                Path(ctx.root) / 'libraries' / 'OS_Symbols.json',
                base_dir / 'OS_Symbols.json',
            ]
        )
        for cand in candidates:
            if cand.exists():
                data = read_json(str(cand))
                if isinstance(data, dict):
                    self._symbols = data
                    break
        self._units_map = self._symbols.get('units', {}) if isinstance(self._symbols.get('units', {}), dict) else {}
        self._states_map = self._symbols.get('states', {}) if isinstance(self._symbols.get('states', {}), dict) else {}
        self.REV_UNIT = {str(v): str(k) for k, v in self._units_map.items()}
        self.REV_STATE = {str(v): str(k) for k, v in self._states_map.items()}

    def compress(self, data):
        if self._rs_solidity is None:
            raise NativeLibraryUnavailable("Rust solidity compressor not available")
        return self._rs_solidity.compress(data)

    def decompress(self, packet):
        if isinstance(packet, (bytes, bytearray, memoryview)):
            packet = bytes(packet).decode('utf-8', errors='ignore')
        text = str(packet)
        main, *msg = text.split('@', 1)
        segs = [s for s in main.split('|') if s]
        if not segs:
            return {}
        head = segs[0].split('.')
        out = {}
        if len(head) >= 3:
            out['id'] = head[0]
            out['s'] = self.REV_STATE.get(head[1], head[1]).upper()
            try:
                ts_raw = base64.urlsafe_b64decode(head[2] + '==')[:6]
                out['t_raw'] = struct.unpack('>Q', b'\x00\x00' + ts_raw)[0]
            except Exception:
                out['t_raw'] = 0

        idx = 1
        for seg in segs[1:]:
            if seg.startswith('&'):
                out['geohash'] = seg[1:]
                continue
            if seg.startswith('#'):
                try:
                    tail = base64.urlsafe_b64decode(seg[1:] + '==').decode()
                    out['url'] = 'https://' + tail
                except Exception:
                    out['url'] = seg[1:]
                continue
            if '>' not in seg or ':' not in seg:
                continue
            sid, rhs = seg.split('>', 1)
            meta, v_enc = rhs.rsplit(':', 1)
            sst, unit_enc = meta.split('.', 1) if '.' in meta else ('U', meta)
            out[f's{idx}_id'] = sid
            out[f's{idx}_s'] = self.REV_STATE.get(sst, sst).upper()
            unit_token = unit_enc.split(',')[-1] if ',' in unit_enc else unit_enc
            out[f's{idx}_u'] = self.REV_UNIT.get(unit_token, unit_token)
            try:
                out[f's{idx}_v'] = self._ffi.decode(v_enc, use_precision=True)
            except Exception:
                out[f's{idx}_v'] = 0.0
            idx += 1

        if msg:
            try:
                out['msg'] = base64.urlsafe_b64decode(msg[0] + '==').decode()
            except Exception:
                out['msg'] = msg[0]
        return out

    def __getattr__(self, name):
        ffi = self.__dict__.get('_ffi')
        if ffi is not None and hasattr(ffi, name):
            return getattr(ffi, name)
        rs_solidity = self.__dict__.get('_rs_solidity')
        if rs_solidity is not None and hasattr(rs_solidity, name):
            return getattr(rs_solidity, name)
        raise AttributeError(f"{self.__class__.__name__} has no attribute '{name}'")
