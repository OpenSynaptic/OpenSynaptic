# Maturin `cffi` Error Root Cause and Final Fix

## What actually failed

CI logs showed:

- `Found cffi bindings`
- then `ModuleNotFoundError: No module named 'cffi'`

At first glance this looks like a missing Python package, but that is only the symptom.

## Confirmed root cause

The Rust crate had:

- `pyo3` behind feature gate `python-module`
- `default = []`

So when CI invoked `maturin build --manifest-path ...` without effective feature activation,
`pyo3` was not compiled in. In that state, maturin did not see PyO3 bindings and entered cffi discovery path, which then failed because `cffi` was not installed in the selected interpreter.

Evidence from this repo:

- `cargo tree -e features` (default) did **not** include `pyo3`
- `cargo tree --features python-module -e features` did include `pyo3`

## Final code fix applied

In `src/opensynaptic/core/rscore/rust/Cargo.toml`:

```toml
[features]
default = ["python-module"]
python-module = ["dep:pyo3"]
```

This makes direct maturin calls deterministic: PyO3 is active by default, so maturin no longer falls back to cffi mode.

Also updated local build docs:

- `src/opensynaptic/core/rscore/rust/README.md`
- build command now explicitly includes `--features python-module`

## CI recommendation

Even with default feature fixed, keep CI explicit:

```bash
python -m maturin build --manifest-path src/opensynaptic/core/rscore/rust/Cargo.toml --release --features python-module
```

If your workflow currently uses `maturin-action`, add equivalent feature args there as well.


