import sys
import time
import math
from pathlib import Path
from opensynaptic.utils import (
    read_json,
    write_json,
    ctx,
    os_log,
)
BASE_DIR = Path(__file__).resolve().parent
LIB_DIR = None
_UNIT_ALIAS_MAP = {'cel': 'Cel', 'hour': 'h', 'celsius': 'degree_celsius'}

class OpenSynapticStandardizer:

    def __init__(self, config_path='Config.json'):
        if config_path and Path(config_path).exists():
            cfg_file = str(Path(config_path).resolve())
            self.config = self._load_json(cfg_file)
            project_root = Path(cfg_file).resolve().parent
        else:
            self.config = ctx.config or {}
            project_root = Path(ctx.root)
        settings = self.config.get('engine_settings', {})
        self.switches = self.config.get('payload_switches', {})
        self.precision = settings.get('precision', 4)
        lib_dir = None
        res_root = self.config.get('RESOURCES', {}).get('root')
        if res_root:
            candidate = Path(project_root) / res_root
            if candidate.exists():
                lib_dir = str(candidate)
            else:
                os_log.warn('STD', 'INIT', f"RESOURCES.root '{res_root}' not found at '{candidate}'; falling back to 'libraries/'")
        if not lib_dir:
            candidate = Path(project_root) / 'libraries'
            if candidate.exists():
                lib_dir = str(candidate)
        if not lib_dir:
            # Package-internal libraries (pip-installed path)
            candidate = BASE_DIR.parent.parent / 'libraries'
            if candidate.exists():
                lib_dir = str(candidate)
        if not lib_dir:
            lib_dir = str(Path(BASE_DIR) / 'OS_Library')
            os_log.warn('STD', 'INIT', f"No unit library directory resolved; using fallback '{lib_dir}' (may not exist)")
        units_dir = Path(lib_dir) / 'Units'
        if not units_dir.is_dir():
            alt = Path(lib_dir) / 'units'
            if alt.is_dir():
                units_dir = alt
        self.lib_units_dir = str(units_dir)
        try:
            if lib_dir not in sys.path:
                sys.path.append(lib_dir)
        except Exception as e:
            os_log.err('STD', 'INIT', e, {'lib_dir': lib_dir})
        # Write cache next to Config.json (user-writable), not inside site-packages
        _cache_base = Path(project_root) / 'cache'
        self.cache_path = str(_cache_base / 'standardization_cache.json')
        Path(self.cache_path).parent.mkdir(parents=True, exist_ok=True)
        cache_data = self._load_json(self.cache_path)
        self.registry = cache_data.get('cached_units', {})
        self._is_dirty = False
        self._units_by_key = {}
        self._units_by_ucum = {}
        p_data_candidates = [Path(lib_dir) / 'Prefixes.json', Path(lib_dir) / 'prefixes.json']
        p_data = {}
        for cand in p_data_candidates:
            if cand.exists():
                p_data = self._load_json(str(cand))
                break
        raw_pre = {**p_data.get('decimal_prefixes', {}), **p_data.get('binary_prefixes', {})}
        self.sorted_prefixes = sorted(raw_pre.keys(), key=len, reverse=True)
        self.prefixes = raw_pre
        self._build_unit_indices()

    def _build_unit_indices(self):
        units_path = Path(self.lib_units_dir)
        if not units_path.is_dir():
            return
        for f in units_path.glob('*.json'):
            data = self._load_json(str(f))
            units = data.get('units', {}) if isinstance(data, dict) else {}
            if not isinstance(units, dict):
                continue
            for u_key, u_info in units.items():
                if u_key not in self._units_by_key:
                    self._units_by_key[u_key] = u_info
                if isinstance(u_info, dict):
                    ucum_code = u_info.get('ucum_code')
                    if isinstance(ucum_code, str) and ucum_code not in self._units_by_ucum:
                        self._units_by_ucum[ucum_code] = u_info

    def _scan_units_fallback(self, target):
        units_path = Path(self.lib_units_dir)
        for f in units_path.glob('*.json'):
            data = self._load_json(str(f))
            units = data.get('units', {})
            if target in units:
                return units[target]
            if target.lower() in units:
                return units[target.lower()]
            for _, u_info in units.items():
                if u_info.get('ucum_code') == target:
                    return u_info
        return None

    def _load_json(self, path):
        return read_json(path)

    def _save_cache(self):
        """Persist cache data to disk."""
        if not self._is_dirty:
            return
        write_json(self.cache_path, {'cached_units': self.registry, 'updated_at': int(time.time()), 'engine': 'OS-Standardizer-v4-GCD-Final'}, indent=4)
        self._is_dirty = False

    def _deep_search_in_atoms(self, unit_str):
        target = unit_str.strip()
        target = _UNIT_ALIAS_MAP.get(target.lower(), target)
        hit = self._units_by_key.get(target)
        if hit is not None:
            return hit
        hit = self._units_by_key.get(target.lower())
        if hit is not None:
            return hit
        hit = self._units_by_ucum.get(target)
        if hit is not None:
            return hit
        # Keep legacy scan as a compatibility fallback.
        return self._scan_units_fallback(target)

    def _resolve_unit_law(self, unit_str):
        if not unit_str or unit_str == 'Unknown':
            return None
        if unit_str in self.registry:
            return self.registry[unit_str]
        orig_label = unit_str
        is_inv = unit_str.startswith('1/')
        work = unit_str[2:] if is_inv else unit_str
        pwr = 1
        if len(work) > 1 and work[-1].isdigit():
            try:
                pwr = int(work[-1])
                work = work[:-1]
            except Exception as e:
                os_log.err('STD', 'PARSE', e, {'unit': unit_str})
        law = self._deep_search_in_atoms(work)
        if not law:
            for pre in self.sorted_prefixes:
                if not isinstance(pre, str):
                    continue
                if work.startswith(pre):
                    base = work[len(pre):]
                    base_law = self._deep_search_in_atoms(base)
                    if base_law and base_law.get('can_take_prefix', True):
                        law = base_law.copy()
                        law['to_standard_factor'] = float(law.get('to_standard_factor', 1.0)) * float(self.prefixes[pre]['f'])
                        break
        if law:
            law = law.copy()
            f = math.pow(float(law.get('to_standard_factor', 1.0)), pwr)
            if is_inv:
                f = 1.0 / f
            res = {'physical_attribute': law.get('physical_attribute', 'Unknown'), 'to_standard_factor': f, 'to_standard_offset': float(law.get('to_standard_offset', 0.0))}
            self.registry[orig_label] = res
            self._is_dirty = True
            return res
        return None

    def standardize(self, device_id, device_status, sensors, **kwargs):
        fact = {'id': device_id, 's': device_status, 't': int(time.time()), **kwargs}
        idx = 1
        for s_data in sensors:
            try:
                s_id, s_st, val, unit_raw = s_data
                u_list = [unit_raw] if isinstance(unit_raw, str) else list(unit_raw)
                laws = [self._resolve_unit_law(str(u)) for u in u_list]
                if not laws or None in laws:
                    continue
                first_law = laws[0]
                f, o = (float(first_law['to_standard_factor']), float(first_law.get('to_standard_offset', 0.0)))
                raw_v = float(val) * f + o
                pfx = f's{idx}'
                fact[f'{pfx}_v'] = int(raw_v) if raw_v.is_integer() else round(raw_v, self.precision)
                num_attr = first_law['physical_attribute']
                den_parts = []
                num_count = 1
                for i in range(1, len(laws)):
                    curr_law = laws[i]
                    if curr_law['physical_attribute'] == num_attr:
                        num_count += 1
                    else:
                        f_val = curr_law['to_standard_factor']
                        f_str = f'{f_val:g}' if f_val != 1 else ''
                        den_parts.append(f"{f_str}{curr_law['physical_attribute']}")
                final_u = f"{num_attr}{(num_count if num_count > 1 else '')}"
                if den_parts:
                    final_u += '/' + '/'.join(den_parts)
                fact[f'{pfx}_u'] = final_u
                if self.switches.get('SensorId'):
                    fact[f'{pfx}_id'] = s_id
                fact[f'{pfx}_s'] = s_st
                idx += 1
            except Exception as e:
                os_log.err('STD', 'STD', e, {'sensor': s_data})
                continue
        if self._is_dirty:
            self._save_cache()
        return fact
