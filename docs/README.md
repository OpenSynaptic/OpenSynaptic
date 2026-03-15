# OpenSynaptic Documentation Index

This folder contains architecture, API, schema, and implementation references for OpenSynaptic.

---

## Start Here

1. [`../README.md`](../README.md) - project overview and quickstart
2. [`ARCHITECTURE.md`](ARCHITECTURE.md) - end-to-end runtime architecture and data flow
3. [`CONFIG_SCHEMA.md`](CONFIG_SCHEMA.md) - `Config.json` key reference
4. [`API.md`](API.md) - public API surface

---

## Runtime and Core References

- [`CORE_API.md`](CORE_API.md) - core facade and backend loader reference
- [`PYCORE_INTERNALS.md`](PYCORE_INTERNALS.md) - Python core internals and method contracts
- [`RSCORE_API.md`](RSCORE_API.md) - Rust backend API reference
- [`PYCORE_RUST_API.md`](PYCORE_RUST_API.md) - Python/Rust interoperability details

---

## Extensibility and Operations

- [`TRANSPORTER_PLUGIN.md`](TRANSPORTER_PLUGIN.md) - transporter and plugin extension guide
- [`ZERO_COPY_CLOSEOUT.md`](ZERO_COPY_CLOSEOUT.md) - zero-copy transport rollout notes

---

## Release Documents

- [`../CHANGELOG.md`](../CHANGELOG.md) - cumulative release history
- [`releases/v0.2.0.md`](releases/v0.2.0.md) - current release draft

---

## Reading Path by Role

- Platform integrator: `README.md` -> `ARCHITECTURE.md` -> `CONFIG_SCHEMA.md`
- Plugin/driver developer: `TRANSPORTER_PLUGIN.md` -> `API.md` -> `PYCORE_INTERNALS.md`
- Runtime maintainer: `CORE_API.md` -> `RSCORE_API.md` -> `ZERO_COPY_CLOSEOUT.md`

