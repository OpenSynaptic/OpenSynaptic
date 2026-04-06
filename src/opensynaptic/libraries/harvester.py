from pathlib import Path
import json
from opensynaptic.utils import (
    write_json,
    os_log,
    LogMsg,
)

CURRENT_DIR = Path(__file__).resolve().parent
UNITS_DIR = CURRENT_DIR / "Units"
if not UNITS_DIR.exists():
    alt = CURRENT_DIR / "units"
    if alt.exists():
        UNITS_DIR = alt


class SymbolHarvester:
    def __init__(self):
        self.output_file = str(CURRENT_DIR / "OS_Symbols.json")

    def sync(self):
        unit_map = {}
        state_map = {
            "online": "1", "offline": "0", "ok": "K",
            "unknown": "Z", "error": "E"
        }

        if not UNITS_DIR.exists():
            os_log.log_with_const("error", LogMsg.LIBRARY_SYNC_FAILED, target=str(UNITS_DIR))
            return {}

        files = [f for f in UNITS_DIR.iterdir() if f.suffix in ('.py', '.json') and f.name != "__init__.py"]

        for f_path in files:
            try:
                with open(f_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)

                metadata = data.get("__METADATA__", {})
                class_symbol = metadata.get("OS_UNIT_SYMBOLS")
                class_name = metadata.get("class_name")  # Extract class name, e.g. Informatics
                units_dict = data.get("units", {})

                if class_symbol is not None:
                    if class_name:
                        unit_map[class_name.lower()] = str(class_symbol)

                    if isinstance(units_dict, dict):
                        for u_key, u_info in units_dict.items():
                            tid = u_info.get("tid", "0x0000")
                            offset = tid[-2:].upper()
                            unit_map[u_key.lower()] = f"{class_symbol}{offset}"

            except Exception as e:
                os_log.err("LIB", "SYNC", e, {"target": f_path.name})
                os_log.log_with_const("error", LogMsg.LIBRARY_SYNC_FAILED, target=f_path.name)

        export_data = {
            "units": unit_map,
            "states": state_map
        }

        write_json(self.output_file, export_data, indent=4)
        os_log.log_with_const("info", LogMsg.LIBRARY_SYNCED, output=self.output_file)
        return export_data


if __name__ == "__main__":
    harvester = SymbolHarvester()
    harvester.sync()
