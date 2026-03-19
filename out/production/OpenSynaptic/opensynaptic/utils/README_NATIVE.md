# Native Utils (ctypes)

This folder contains the C acceleration sources used by:

- `opensynaptic.utils.base62`
- `opensynaptic.utils.security_core`

## Files

- `base62_native.c`
- `security_native.c`
- `build_native.py`
- `check_native_toolchain.py`
- `native_loader.py`

## Build

```powershell
python -u src/opensynaptic/utils/c/check_native_toolchain.py
python -u src/opensynaptic/utils/c/build_native.py
```

The build outputs shared libraries to `src/opensynaptic/utils/c/bin/`.

## Runtime

`native_loader.py` tries:

1. `OPENSYNAPTIC_NATIVE_DIR` (if set)
2. `src/opensynaptic/utils/c/bin/`
3. `src/opensynaptic/utils/c/`

If native libraries are unavailable, `Base62Codec` / security helpers raise a native-library error.

`OPENSYNAPTIC_AUTO_BUILD_NATIVE` defaults to `0` (disabled). Set it to `1` to attempt auto-build at runtime.

