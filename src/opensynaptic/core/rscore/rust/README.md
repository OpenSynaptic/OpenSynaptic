# opensynaptic-rscore

Rust acceleration wheel for OpenSynaptic.

This crate keeps the existing C ABI exports used by `ctypes` and also exposes
an optional PyO3 extension module (`opensynaptic_rscore._native`) for wheel
builds driven by `maturin`.

Build wheel locally:

```powershell
py -3 -m pip install maturin
py -3 -m maturin build --manifest-path src/opensynaptic/core/rscore/rust/Cargo.toml --release --features python-module
```

