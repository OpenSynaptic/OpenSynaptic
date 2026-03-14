import base64, time, struct
from pathlib import Path
from opensynaptic.utils.paths import read_json, ctx
from opensynaptic.utils.base62_codec import Base62Codec
from opensynaptic.utils.logger import os_log

class OpenSynapticEngine:

    def __init__(self, config_path=None):
        if config_path:
            final_path = config_path
            self.config = read_json(final_path) or {}
            base_path = str(Path(final_path).parent)
        else:
            self.config = ctx.config or {}
            base_path = ctx.root
        self.registry_root = getattr(ctx, 'registry_dir', None)
        settings = self.config.get('engine_settings', {})
        precision = settings.get('precision', 4)
        self.codec = Base62Codec(precision=precision)
        self.precision_val = 10 ** precision
        self.BIT_SWITCH = {'0x10': {'macro': 'da', 'micro': 'd', 'f': 10}, '0x20': {'macro': 'k', 'micro': 'm', 'f': 1000}, '0x40': {'macro': 'M', 'micro': 'u', 'f': 1000000}, '0x80': {'macro': 'G', 'micro': 'p', 'f': 1000000000}}
        self.SCALE_MAP = {}
        for v in self.BIT_SWITCH.values():
            self.SCALE_MAP[v['macro']] = v['f']
        for v in self.BIT_SWITCH.values():
            self.SCALE_MAP[v['micro']] = 1.0 / v['f']
        res = self.config.get('RESOURCES', {})
        sym_ref = res.get('prefixes') or res.get('symbols')
        if sym_ref:
            self.sym_path = str(Path(base_path) / sym_ref)
        else:
            self.sym_path = str(Path(base_path) / 'data' / 'symbols.json')
        self.sol_path = str(Path(base_path) / 'cache' / 'solidity_cache.json')
        settings = self.config.get('engine_settings', {})
        self.USE_MS = settings.get('use_ms', True)
        self.precision_val = 10 ** settings.get('precision', 4)
        self.CHARS = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
        self._symbols_cache = None
        self.registry = read_json(self.sol_path).get('cached_units', {})
        self._refresh_maps()

    def _load_json(self, path):
        return read_json(path)

    def _refresh_maps(self):
        lib = self._load_json(self.sym_path)
        self.REV_UNIT = {str(v): k for k, v in lib.get('units', {}).items()}
        for k, v in self.registry.items():
            sym = v.get('os_symbol')
            if sym:
                self.REV_UNIT[str(sym)] = k
        self.REV_STATE = {str(v): k for k, v in lib.get('states', {}).items()}
        self._symbols_cache = lib

    def _get_symbol(self, key, map_type='units'):
        k_low = str(key).lower()
        lib = self._symbols_cache
        if not lib:
            try:
                lib = self._load_json(self.sym_path)
                self._symbols_cache = lib
            except Exception as e:
                os_log.err('ENG', 'IO', e, {'sym_path': self.sym_path})
                return key
        return lib.get(map_type, {}).get(k_low, key)

    def encode_b62(self, n, use_precision=True):
        return self.codec.encode(n, use_precision=use_precision)

    def decode_b62(self, s, use_precision=True):
        return self.codec.decode(s, use_precision=use_precision)

    def _split_coeff_attr_power(self, p):
        s = (p or '').strip()
        if not s:
            return (None, '', '')
        i = len(s) - 1
        while i >= 0 and s[i].isdigit():
            i -= 1
        pwr = s[i + 1:] if i < len(s) - 1 else ''
        core = s[:i + 1]
        coeff = None
        attr = core
        last_ok = 0
        for j in range(1, len(core) + 1):
            try:
                float(core[:j])
                last_ok = j
            except Exception:
                continue
        if last_ok > 0 and last_ok < len(core):
            coeff = core[:last_ok]
            attr = core[last_ok:]
        elif last_ok == len(core):
            coeff = core
            attr = ''
        return (coeff, attr, pwr)

    def _strip_sym_and_power(self, sym_p):
        """Split a symbol+power like 'kg2' into ('kg','2') without regex."""
        s = (sym_p or '').strip()
        if not s:
            return ('', '')
        i = len(s) - 1
        while i >= 0 and s[i].isdigit():
            i -= 1
        base = s[:i + 1]
        pwr = s[i + 1:] if i < len(s) - 1 else ''
        return (base, pwr)

    def _compress_unit(self, unit_str):
        if not unit_str or unit_str == 'unknown':
            return 'Z'
        parts = unit_str.split('/')
        compressed = []
        for p in parts:
            coeff, attr, pwr = self._split_coeff_attr_power(p)
            if attr is None:
                continue
            p_suffix = pwr if pwr else ''
            if coeff:
                try:
                    c_val = float(coeff)
                except Exception:
                    compressed.append(self._get_symbol(attr, 'units') + p_suffix)
                    continue
                final_attr = attr
                for mask, info in sorted(self.BIT_SWITCH.items(), key=lambda x: x[1]['f'], reverse=True):
                    f = info['f']
                    if c_val >= f and c_val % f == 0:
                        c_val /= f
                        final_attr = info['macro'] + attr
                        break
                sym = self._get_symbol(final_attr, 'units')
                is_direct = c_val == int(c_val) and abs(c_val) >= 1
                c_enc = self.encode_b62(c_val, use_precision=not is_direct)
                compressed.append(f'{c_enc},{sym}{p_suffix}')
            else:
                compressed.append(self._get_symbol(attr, 'units') + p_suffix)
        return '/'.join(compressed)

    def compress(self, data):
        t_in = data.get('t', time.time() * (1000 if self.USE_MS else 1))
        t_raw = int(t_in * 1000) if self.USE_MS and t_in < 10 ** 11 else int(t_in)
        t_bin = struct.pack('>Q', t_raw)[2:]
        t_enc = base64.urlsafe_b64encode(t_bin).decode().rstrip('=')
        s_sym = self._get_symbol(data.get('s', 'U'), 'states')
        header = f"{data['id']}.{s_sym}.{t_enc}|"
        segs = []
        i = 1
        while f's{i}_id' in data:
            p = f's{i}'
            un = self._compress_unit(str(data.get(f'{p}_u', '')))
            v = self.encode_b62(data.get(f'{p}_v', 0))
            sst = self._get_symbol(data.get(f'{p}_s', 'U'), 'states')
            segs.append(f"{data[f'{p}_id']}>{sst}.{un}:{v}|")
            i += 1
        extra = ''
        if 'geohash' in data:
            extra += f"&{data['geohash']}|"
        if 'url' in data:
            u_b64 = base64.urlsafe_b64encode(data['url'].replace('https://', '').encode()).decode().rstrip('=')
            extra += f'#{u_b64}|'
        body = f"{header}{''.join(segs)}{extra}"
        if 'msg' in data:
            body += '@' + base64.urlsafe_b64encode(data['msg'].encode()).decode().rstrip('=')
        return body

    def decompress(self, packet):
        try:
            main, *msg = packet.split('@', 1)
            all_segs = [s for s in main.split('|') if s]
            h_parts = all_segs[0].split('.')
            t_bin = base64.urlsafe_b64decode(h_parts[2] + '==')
            t_raw_val = struct.unpack('>Q', b'\x00\x00' + t_bin)[0]
            res = {'id': h_parts[0], 's': self.REV_STATE.get(h_parts[1], h_parts[1]).upper(), 't_raw': t_raw_val}
            for s in all_segs[1:]:
                if s.startswith('&'):
                    res['geohash'] = s[1:]
                elif s.startswith('#'):
                    res['url'] = 'https://' + base64.urlsafe_b64decode(s[1:] + '==').decode()
                elif '>' in s:
                    sid, pay = s.split('>', 1)
                    if ':' not in pay:
                        continue
                    sst_u, v_enc = pay.rsplit(':', 1)
                    if '.' in sst_u:
                        parts = sst_u.split('.', 1)
                        sst_sym, u_enc = (parts[0], parts[1])
                    else:
                        sst_sym, u_enc = ('U', sst_u)
                    u_list = []
                    if u_enc:
                        for up in u_enc.split('/'):
                            if not up:
                                continue
                            target_up = up.split(',')[-1] if ',' in up else up
                            if ',' in up and any((c.isdigit() for c in up.split(',')[0])):
                                try:
                                    c_e, sym_p = up.split(',', 1)
                                    sym, pwr = self._strip_sym_and_power(sym_p)
                                    if '.' in c_e or 'e' in c_e.lower():
                                        c = float(c_e)
                                    else:
                                        try:
                                            c = self.decode_b62(c_e, False)
                                        except Exception:
                                            c = float(c_e)
                                    pfx = next((p for p in self.SCALE_MAP if sym.startswith(p)), None)
                                    f_c = c * self.SCALE_MAP[pfx] if pfx else c
                                    f_u = self.REV_UNIT.get(sym[len(pfx):] if pfx else sym, sym)
                                    u_list.append(f"{(int(f_c) if f_c == int(f_c) else f_c)}{f_u}{(pwr if pwr else '')}")
                                except Exception:
                                    u_list.append(self.REV_UNIT.get(target_up, target_up))
                            else:
                                u_list.append(self.REV_UNIT.get(target_up, target_up))
                    idx = len([k for k in res if '_id' in k]) + 1
                    res.update({f's{idx}_id': sid, f's{idx}_s': self.REV_STATE.get(sst_sym, sst_sym).upper(), f's{idx}_u': '/'.join(u_list), f's{idx}_v': self.decode_b62(v_enc, True)})
            if msg:
                res['msg'] = base64.urlsafe_b64decode(msg[0] + '==').decode()
            return res
        except Exception as e:
            return os_log.err('ENG', 'DEC', e, packet)
