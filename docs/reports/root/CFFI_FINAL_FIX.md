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

## New issue: `Large file option has not been set`

### Symptom

During `python -m build`, wheel build failed with:

```text
Failed to write to zip archive for "opensynaptic/core/rscore/rust/target/wheels/opensynaptic-...whl"
Caused by: Large file option has not been set
```

### Root cause

For this mixed project (`python-source = "src"`, package `opensynaptic`), Rust default
build output location was under package source tree:

`src/opensynaptic/core/rscore/rust/target/...`

That allowed wheel artifacts to live inside files considered for packaging, creating a
self-inclusion/feedback-loop risk during wheel assembly.

### Final fix

Added Cargo config:

`src/opensynaptic/core/rscore/rust/.cargo/config.toml`

```toml
[build]
target-dir = "../../../../../target/rscore"
```

This moves Rust outputs outside `src/opensynaptic/**`, preventing recursive inclusion and
stabilizing `maturin pep517 build-wheel`.


