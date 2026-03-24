# OpenSynaptic Docs Hub

This is the canonical navigation hub for project documentation.
If you only open one docs file first, use this one.

---

## Core References

- `../README.md` - project overview, installation, CLI quick reference
- `ARCHITECTURE.md` - system architecture and processing pipeline
- `CONFIG_SCHEMA.md` - `Config.json` schema and runtime keys
- `API.md` - public API contracts and examples
- `CORE_API.md` - core facade, backend discovery, and symbol resolution

---

## Backend and Runtime Internals

- `internal/PYCORE_INTERNALS.md` - Python core internals
- `RSCORE_API.md` - Rust backend API behavior
- `PYCORE_RUST_API.md` - Python and Rust boundary details
- `internal/ZERO_COPY_CLOSEOUT.md` - zero-copy transport rollout and constraints

---

## Plugins, Transporters, and Operations

- `TRANSPORTER_PLUGIN.md` - transporter extension model and contract
- `ID_LEASE_SYSTEM.md` - ID lifecycle and lease policy behavior
- `ID_LEASE_CONFIG_REFERENCE.md` - lease tuning and config presets

---

## Release and Change Documents

- `../CHANGELOG.md` - full project changelog
- `releases/v0.1.1.md`
- `releases/v0.2.0.md`
- `releases/v1.1.0.md`
- `releases/v0.3.0_announcement.md`
- `releases/announcement-summary-v0.3.0.md`
- `reports/releases/v0.2.0-v0.3.0-comparison.md`
- `guides/upgrade/v0.3.0.md`
- `guides/drivers/quick-reference.md`

---

## Reading Paths

### New team member

1. `../README.md`
2. `ARCHITECTURE.md`
3. `CONFIG_SCHEMA.md`

### Backend maintainer

1. `CORE_API.md`
2. `internal/PYCORE_INTERNALS.md`
3. `PYCORE_RUST_API.md`
4. `RSCORE_API.md`

### Integrations and drivers

1. `TRANSPORTER_PLUGIN.md`
2. `API.md`
3. `guides/drivers/quick-reference.md`

### Operations and deployment

1. `ID_LEASE_SYSTEM.md`
2. `ID_LEASE_CONFIG_REFERENCE.md`
3. `guides/upgrade/v0.3.0.md`

---

## Documentation Maintenance Rules

- Keep English as the canonical language for actively maintained docs.
- Keep topic docs in `docs/`; keep release snapshots in `docs/releases/`.
- Keep non-publish process and status documents in `docs/internal/`.
- Avoid duplicate feature explanations across multiple files.
- Prefer linking to one canonical doc instead of copy-pasting sections.
- Keep command examples executable and tagged as `powershell`.

For repository-wide navigation, see `INDEX.md`.

Maintainer-only records are grouped under `internal/` (see `internal/README.md`).

