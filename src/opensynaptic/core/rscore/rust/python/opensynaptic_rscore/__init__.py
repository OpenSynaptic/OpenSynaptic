"""Python wrapper for the opensynaptic-rscore Rust extension."""


def abi_info_py():
	raise RuntimeError("opensynaptic-rscore extension is not installed")

try:
	from . import _native as _native
except Exception as _IMPORT_ERROR:  # pragma: no cover - extension may be absent in source tree
	_LOAD_ERROR = _IMPORT_ERROR
else:
	abi_info_py = _native.abi_info_py

__all__ = ["abi_info_py"]

