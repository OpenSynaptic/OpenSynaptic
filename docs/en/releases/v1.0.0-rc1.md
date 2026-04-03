# OpenSynaptic v1.0.0-rc1 Release Notes

Release date: 2026-03-26  
Type: Release candidate (packaging hardening + transporter expansion + docs and audit alignment)

---

## Highlights

- Prepared a release-candidate packaging baseline for Python and Rust distribution workflows.
- Added new application-layer gateway transporters: Matter and Zigbee.
- Added a new physical-layer gateway protocol: Bluetooth.
- Extended driver capability audits to cover Matter, Zigbee, and Bluetooth.
- Updated schema and transporter docs to reflect new protocol coverage and config defaults.

---

## Scope Summary

This RC focuses on release readiness and protocol surface expansion:

- Packaging and release automation for cross-platform delivery.
- Runtime transporter matrix expansion (L7 + PHY).
- Config/default-map synchronization across core, CLI, and root config templates.
- Documentation and audit-tool consistency updates.

No wire-format breaking change is introduced in this RC scope.

---

## Added

### Packaging and Release Infrastructure

- Added root `LICENSE` (MIT).
- Added CI workflow ` .github/workflows/ci.yml` for matrix testing/build tasks.
- Added tag-driven release workflow `.github/workflows/release.yml` for artifact publishing pipelines.
- Added Rust wheel packaging scaffold under `src/opensynaptic/core/rscore/rust/`:
  - `pyproject.toml` for maturin build backend
  - `README.md` for local build usage
  - PyO3 module entrypoint integration in `src/lib.rs`

### Baseline Test Suite

- Added `tests/unit/test_core_algorithms.py` (CRC/Base62/packet encode-decode checks).
- Added `tests/integration/test_pipeline_e2e.py` (end-to-end virtual sensor pipeline roundtrip).
- Added `tests/README.md` with local test invocation guidance.

### New Transporters / Protocols

- Added application-layer driver: `src/opensynaptic/services/transporters/drivers/matter.py`.
- Added application-layer driver: `src/opensynaptic/services/transporters/drivers/zigbee.py`.
- Added physical-layer protocol: `src/opensynaptic/core/physical_layer/protocols/bluetooth.py`.

---

## Changed

### Packaging Metadata and Build Configuration

- Updated `pyproject.toml` with release-facing metadata:
  - version set for release-candidate line
  - readme/license/requires-python/classifiers/keywords
  - `dev` and `rscore` optional dependency groups
  - pytest/coverage tool sections
- Updated package-data config to include native source files:
  - `opensynaptic.utils.base62/*.c`
  - `opensynaptic.utils.security/*.c`

### Transporter Discovery and Defaults

- Updated application-layer driver allowlist in `src/opensynaptic/services/transporters/main.py`:
  - now includes `mqtt`, `matter`, `zigbee`
- Updated app protocol map in `src/opensynaptic/core/pycore/transporter_manager.py` to include `matter`, `zigbee`.
- Updated physical protocol candidates in `src/opensynaptic/core/physical_layer/manager.py` to include `bluetooth`.
- Updated default config seeding in:
  - `src/opensynaptic/core/pycore/core.py`
  - `src/opensynaptic/CLI/app.py`
  to include status/config defaults for `matter`, `zigbee`, and `bluetooth`.
- Updated root `Config.json` with corresponding status/config keys and merged mirror entries.

### Completion and UX

- Updated transporter completion descriptions in `src/opensynaptic/CLI/completion.py` for:
  - `matter`
  - `zigbee`
  - `bluetooth`

---

## Audit Coverage Updates

Driver capability audit coverage was expanded in both script and plugin paths:

- `scripts/audit_driver_capabilities.py`
- `src/opensynaptic/services/test_plugin/audit_driver_capabilities.py`

Added audit targets:

- L7: `Matter`, `Zigbee`
- PHY: `Bluetooth`

---

## Documentation Updates

- Updated `docs/TRANSPORTER_PLUGIN.md`:
  - protocol examples now include Matter/Zigbee (application layer) and Bluetooth (physical layer)
  - corrected Bluetooth physical driver path example
- Updated `docs/CONFIG_SCHEMA.md`:
  - `application_status` now documents MQTT/Matter/Zigbee
  - `physical_status` now documents Bluetooth
  - expanded `application_config` and `physical_config` examples

---

## Validation Performed

### Test Suite

```powershell
py -3 -m pytest tests -q
```

Observed result during RC preparation: `4 passed`.

### Driver Capability Audit

```powershell
py -3 -u scripts/audit_driver_capabilities.py
```

Observed result during RC preparation:

- Complete drivers: 13
- Incomplete drivers: 0
- Error: 0

### Distribution Validation

```powershell
py -3 -m maturin sdist --manifest-path src/opensynaptic/core/rscore/rust/Cargo.toml --out dist
py -3 -m maturin build --manifest-path src/opensynaptic/core/rscore/rust/Cargo.toml --release --out dist
py -3 -m twine check dist/*
```

Observed result during RC preparation: distribution checks passed.

---

## Known Constraints in RC-1

- Matter/Zigbee/Bluetooth implementations are gateway-oriented socket shims, not full native protocol stacks.
- Zigbee and Bluetooth direct radio/coordinator behavior still depends on external hardware gateways or dedicated stacks.
- Tag-based publishing jobs require repository secrets and release environment setup.

---

## Migration Notes

If upgrading existing configs, ensure these keys exist under `RESOURCES`:

- `application_status.matter`
- `application_status.zigbee`
- `application_config.matter`
- `application_config.zigbee`
- `physical_status.bluetooth`
- `physical_config.bluetooth`
- `transporters_status` mirror entries for the same keys

Core and CLI default bootstrap now seed these values for new or auto-repaired configs.

---

## Next Steps Toward GA

- Stabilize a formal gateway bridge profile (for Zigbee <-> other transport flows).
- Add protocol-specific conformance tests for Matter/Zigbee/Bluetooth gateway adapters.
- Finalize release pipeline permissions and tag policy for public publishing.

