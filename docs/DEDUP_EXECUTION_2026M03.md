# Dedup Execution Report (2026-03)

This report captures the completed phase-1..phase-5 work for project-wide deduplication and size reduction.

Constraints respected:
- No edits were made under `libraries/`.
- External behavior, CLI output shape, and JSON schema were preserved.

## Phase 1 - Baseline and duplicate inventory (read-only)

### Scope baseline (Python files)

| Scope | Files | Lines |
|---|---:|---:|
| `src/opensynaptic/core/pycore` | 7 | 2018 |
| `src/opensynaptic/core/rscore` | 11 | 2087 |
| `src/opensynaptic/services` | 33 | 5486 |
| `src/opensynaptic/CLI` | 12 | 1941 |
| `plugins` | 2 | 487 |
| `scripts` | 4 | 286 |
| **Total** | **69** | **12305** |

### Duplicate block estimate

- Normalized 8-line duplicate-window scan:
  - `repeated_blocks = 47`
  - `files_with_repeats = 14`

### Risk-graded hotspot list

Low risk (safe to dedup):
- Name normalization (`str(...).strip().lower()`) repeated across managers and loader.
- Wire payload preparation (`zero-copy` decision) repeated in multiple send paths.
- Script bootstrap path wiring repeated in smoke scripts.
- Proxy-driver object reallocation in transporter manager.

Medium risk (safe with per-step tests):
- Resource-map migration loops in `pycore/transporter_manager.py`.
- `rscore` wrapper boilerplate (`_ffi` ctor guards, passthrough, `__getattr__`).
- Parser input coercion boilerplate in `pycore/unified_parser.py`.

High risk (deferred/guarded):
- Cross-backend parity semantics in `rscore` packet behavior.
- Handshake/data-path semantics tied to Rust internals.

### Performance baseline (captured)

Stress baseline:
- command: `plugin-test --suite stress --total 200 --workers 8 --sources 6 --no-progress`
- result: `ok=200`, `fail=0`, `throughput_pps=16147.3`, `p95_latency_ms=0.543`

Compare baseline:
- command: `plugin-test --suite compare --total 1000 --workers 8 --runs 1 --warmup 0 --no-progress`
- result:
  - `pycore throughput_pps_avg=10229.5`, `p95_latency_ms_avg=0.0962`, `fail=0`
  - `rscore throughput_pps_avg=19444.9`, `p95_latency_ms_avg=0.4061`, `fail=0`

## Phase 2 - Low-risk size reduction

Completed:
- Removed redundant build mirror directory: `out/production/**`.
- Expanded dead-code and duplicate-helper cleanup in core/service/test-plugin paths.

Safety checks:
- No source references to `out/production` remained before removal.
- Smoke/component checks still pass with the existing known baseline failures unchanged.

## Phase 3 - Transport path dedup (decoupled)

Completed single-point consolidation:
- Added shared `to_wire_payload(...)` helper in `src/opensynaptic/utils/buffer.py`.
- Reused by:
  - `src/opensynaptic/core/layered_protocol_manager.py`
  - `src/opensynaptic/services/transporters/main.py`
  - `src/opensynaptic/core/pycore/core.py`
- Kept legacy `transporters_status` mirror behavior in `pycore/transporter_manager.py`.

Also completed:
- `TransporterManager` now avoids private manager internals in runtime refresh.
- Proxy instances are cached to avoid repeated allocations.

## Phase 4 - rscore wrapper consolidation

Completed with shared proxy base:
- Added `src/opensynaptic/core/rscore/_ffi_proxy.py`.
- Migrated wrappers to shared boilerplate:
  - `src/opensynaptic/core/rscore/core.py`
  - `src/opensynaptic/core/rscore/handshake.py`
  - `src/opensynaptic/core/rscore/standardization.py`
  - `src/opensynaptic/core/rscore/unified_parser.py`
  - `src/opensynaptic/core/rscore/transporter_manager.py`

Behavior preserved:
- Same constructor guard semantics (`NativeLibraryUnavailable` on unavailable rust facade).
- Same method signatures and forwarding behavior.

## Phase 5 - Script entry and docs convergence

Completed:
- Added shared bootstrap helper: `src/opensynaptic/utils/script_bootstrap.py`.
- Updated script entrypoints to reuse it:
  - `scripts/concurrency_smoke.py`
  - `scripts/core_hard_switch_smoke.py`

Documentation convergence:
- This report acts as the landed-state ledger for baseline, risk map, and completed refactors.

## Verification summary

Executed and passing during rollout:
- `python -u scripts/core_hard_switch_smoke.py`
- `python -u scripts/concurrency_smoke.py 60 4 4`
- `python -u src/main.py plugin-test --suite stress --total 20 --workers 2 --sources 2 --no-progress`
- `python -u -m unittest opensynaptic.services.test_plugin.component_tests.TestCoreManager`
- `python -u -m unittest opensynaptic.services.test_plugin.component_tests.TestOSVisualFusionEngine`

Component suite status note:
- `plugin-test --suite component` still reports the same known 4 `TestRscoreFusionEngine` parity failures seen before these changes.
- No new failures were introduced in touched areas.

