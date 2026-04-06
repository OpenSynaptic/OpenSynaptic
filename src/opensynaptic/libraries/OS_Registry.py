from datetime import datetime
from pathlib import Path
from opensynaptic.utils import (
    read_json,
    os_log,
    LogMsg,
)


class OS_Registry:
    # Mode constants (enum-style for faster branch checks)
    MODE_OFF = 0
    MODE_ON = 1
    MODE_AUTO = 2

    def __init__(self, boot_config_path="Library_Config.json"):
        self.base_dir = Path(__file__).resolve().parent
        boot_cfg = self._load_json(boot_config_path)
        paths = boot_cfg.get("PATHS", {})
        settings = boot_cfg.get("SETTINGS", {})

        self.spec_path = paths.get("protocol_spec", "Protocol_Spec.json")
        self.units_dir = paths.get("units_repository", "Units")
        self.spec = self._load_json(self.spec_path)

        mode_str = settings.get("matrix_resolve_mode", "AUTO").upper()
        self._mode = {"OFF": 0, "ON": 1, "AUTO": 2}.get(mode_str, 2)

        self.atomic_map = {}
        self.ucum_to_id = {}
        self.unit_detail_map = {}
        self._build_dual_index()

    def _load_json(self, path):
        p = Path(path)
        if not p.is_absolute():
            p = self.base_dir / p
        if not p.exists():
            return {}
        return read_json(str(p))

    def _build_dual_index(self):
        units_path = Path(self.units_dir)
        if not units_path.is_absolute():
            units_path = self.base_dir / units_path
        if not units_path.exists():
            alt = self.base_dir / "Units"
            if alt.exists():
                units_path = alt
        if not units_path.exists():
            return
        for f in units_path.glob("*.json"):
            data = self._load_json(str(f))
            cid = int(data.get("__METADATA__", {}).get("class_id", "0x00"), 16)
            units = data.get("units", {})
            base_found = False
            for u_key, u_info in units.items():
                ucum = u_info.get("ucum_code", u_key)
                entry = {**u_info, "ucum": ucum, "class_id": cid}
                self.unit_detail_map[ucum] = entry
                if not base_found and float(u_info.get("to_standard_factor", 0)) == 1.0:
                    self.atomic_map[cid] = entry
                    self.ucum_to_id[ucum] = cid
                    base_found = True

    def resolve(self, byte1, byte2):
        base_info = self.atomic_map.get(byte1)
        if not base_info: return None, "Unknown"

        if self._mode == 2:  # AUTO
            return self._matrix_resolve(base_info, byte2) if byte2 else (base_info, base_info["ucum"])
        if self._mode == 1:  # ON
            return self._matrix_resolve(base_info, byte2)
        return base_info, base_info["ucum"]  # OFF

    def _matrix_resolve(self, base_info, byte2):
        ucum = base_info["ucum"]
        mode = "micro" if byte2 & 0x08 else "macro"
        scales = self.spec["BIT_SWITCH"]["SCALES"]

        prefix = "".join([scales[m][mode] for m in sorted(scales.keys()) if byte2 & int(m, 16)])
        suffix = "3" if byte2 & 0x04 else ("2" if byte2 & 0x02 else "")
        label = f"{prefix}{ucum}{suffix}"
        if byte2 & 0x01: label = f"1/{label}"
        return base_info, label

    def lookup(self, ucum_code):
        """Return full unit info for any ucum_code, including operation units.

        Returns the unit dict (with class_id, tid, direction, requires_value, etc.)
        or None if not found.
        """
        return self.unit_detail_map.get(ucum_code)

    def compose(self, ucum_base, prefix="", suffix="", inv=False):
        byte1 = self.ucum_to_id.get(ucum_base)
        if byte1 is None: return None, None

        byte2 = 0x00
        scales = self.spec["BIT_SWITCH"]["SCALES"]
        for m_str, p_pair in scales.items():
            if prefix == p_pair["macro"]:
                byte2 |= int(m_str, 16)
                break
            elif prefix == p_pair["micro"]:
                byte2 |= int(m_str, 16)
                byte2 |= 0x08  # Enable Shift bit
                break

        if suffix == "2": byte2 |= 0x02
        if suffix == "3": byte2 |= 0x04
        if inv: byte2 |= 0x01
        return byte1, byte2

    def export_c_header(self, output_path="os_protocol_map.h"):
        lines = [
            "/* OpenSynaptic Protocol Map - Auto Generated */",
            f"/* Generated at: {datetime.now().isoformat()} */",
            "#ifndef OS_PROTOCOL_MAP_H", "#define OS_PROTOCOL_MAP_H\n"
        ]

        lines.append("// Global Class IDs")
        for cid, info in self.atomic_map.items():
            const_name = f"OS_ID_{info['ucum'].upper()}"
            lines.append(f"#define {const_name:<20} {hex(cid)}")

        lines.append("\n// Matrix Logic Masks")
        lines.append("#define OS_MASK_INV          0x01")
        lines.append("#define OS_MASK_GEOM_2       0x02")
        lines.append("#define OS_MASK_GEOM_3       0x04")
        lines.append("#define OS_MASK_SHIFT_MICRO  0x08")

        lines.append("\n#endif")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write("\n".join(lines))
        os_log.log_with_const("info", LogMsg.LIBRARY_HEADER_EXPORTED, output=output_path)
