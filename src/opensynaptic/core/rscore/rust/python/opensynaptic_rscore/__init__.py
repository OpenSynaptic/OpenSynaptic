"""Python wrapper for the opensynaptic-rscore Rust extension."""


def abi_info_py():
	raise RuntimeError("opensynaptic-rscore extension is not installed")

# When built as a wheel by maturin, the extension is packaged under the
# Cargo lib name (opensynaptic_rscore).  In source/editable installs the
# module may be built as _native.  Try both so the shim works everywhere.
_LOAD_ERROR = None
for _ext_name in ('opensynaptic_rscore', '_native'):
	try:
		import importlib as _il
		_ext = _il.import_module('.' + _ext_name, package=__name__)
		abi_info_py = _ext.abi_info_py
		del _ext, _ext_name, _il
		break
	except Exception as _e:
		_LOAD_ERROR = _e

__all__ = ["abi_info_py"]

