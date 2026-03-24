# Core API Guide

This document describes the hard-switched core API.

> **See also:**
> - [`internal/PYCORE_INTERNALS.md`](internal/PYCORE_INTERNALS.md) — complete method-level reference for every class in `pycore/`
> - [`RSCORE_API.md`](RSCORE_API.md) — Rust core (`rscore/`) API design derived from pycore
> - [`API.md`](API.md) — full public API reference including services and plugins

## Public Core Surface

Import from `opensynaptic.core` only:

```python
from opensynaptic.core import (
    get_core_manager,
    OpenSynaptic,
    OpenSynapticStandardizer,
    OpenSynapticEngine,
    OSVisualFusionEngine,
    OSHandshakeManager,
    TransporterManager,
    CMD,
)
```

Only core symbols are exported. Service/plugin internals are not re-exported.

`get_core_manager()` is the management entrypoint for discovering and selecting core plugins.

## Core Layout (Hard Switch)

- Core implementation package: `src/opensynaptic/core/pycore/`
- Public facade package: `src/opensynaptic/core/__init__.py`
- Core plugin manager: `src/opensynaptic/core/coremanager.py`
- Lazy plugin registry: `src/opensynaptic/core/loader.py`
- Legacy per-module core import paths were removed intentionally.

Example:

```python
from opensynaptic.core import OpenSynaptic

node = OpenSynaptic(config_path='E:/OpenSynaptic/OpenSynaptic/Config.json')

manager = get_core_manager()
print(manager.available_cores())
manager.set_active_core('pycore')
```

## Native C (ctypes) Acceleration

`base62.py` and `security_core.py` are native-only ctypes bindings.

- `src/opensynaptic/utils/base62/base62_native.c` -> `os_base62.dll` / `.so` / `.dylib`
- `src/opensynaptic/utils/security/security_native.c` -> `os_security.dll` / `.so` / `.dylib`
- Native loader: `src/opensynaptic/utils/c/native_loader.py`

Build native libraries manually:

```powershell
python -u src/opensynaptic/utils/c/check_native_toolchain.py
python -u src/opensynaptic/utils/c/build_native.py
```

Disable runtime auto-build:

```powershell
$env:OPENSYNAPTIC_AUTO_BUILD_NATIVE = "0"
```

Enable auto-build explicitly (default is disabled):

```powershell
$env:OPENSYNAPTIC_AUTO_BUILD_NATIVE = "1"
```

Set custom native binary directory:

```powershell
$env:OPENSYNAPTIC_NATIVE_DIR = "E:\path\to\native\bin"
```

## Breaking Change Notes

- Removed import paths such as `opensynaptic.core.core`, `opensynaptic.core.solidity`, `opensynaptic.core.handshake`.
- Use `opensynaptic.core` exports only.
- Base62 and security logic no longer have Python algorithm fallbacks; native libraries are required for those code paths.
