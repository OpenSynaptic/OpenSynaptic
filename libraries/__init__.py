import importlib
from pathlib import Path

from opensynaptic.utils import (
    LogMsg,
    os_log,
)


PKG_DIR = Path(__file__).resolve().parent
UNITS_DIR = PKG_DIR / "Units"
if not UNITS_DIR.exists():
    alt = PKG_DIR / "units"
    if alt.exists():
        UNITS_DIR = alt
RUNTIME_CACHE = PKG_DIR / "Units_Runtime_Library.json"
_KNOWN_MODULES = ("harvester", "OS_Registry")


def __getattr__(name):
    for module_name in _KNOWN_MODULES:
        try:
            module = importlib.import_module("libraries.{}".format(module_name))
            if hasattr(module, name):
                return getattr(module, name)
        except Exception as exc:
            os_log.err("LIB", "LOAD", exc, {"module": module_name})
            os_log.log_with_const("warning", LogMsg.LIBRARY_INDEX_FAILED, module=module_name)
    raise AttributeError(name)


os_log.log_with_const("info", LogMsg.LIBRARY_INDEXED, modules=", ".join(_KNOWN_MODULES))

__all__ = ["UNITS_DIR", "RUNTIME_CACHE", "SymbolHarvester", "OS_Registry"]
