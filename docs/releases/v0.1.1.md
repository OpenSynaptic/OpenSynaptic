# OpenSynaptic v0.1.1 Release Notes

Release date: 2026-03-16  
Type: Documentation + concurrency and RS core capability clarification

---

## Highlights

- Added a complete release note for `v0.1.1` that consolidates multi-process and RS core guidance.
- Clarified stress-test concurrency controls and auto-profiling workflow.
- Clarified `rscore` (Rust core) build/check/switch workflow and fallback behavior.
- Updated documentation navigation to point to this release.

---

## Multi-Process and Concurrency Updates

`plugin-test` now has explicit concurrency controls documented and ready for tuning:

- `--processes`: number of OS processes for stress execution (`1` means thread-only mode).
- `--threads-per-process`: thread count in each process (defaults to `--workers`).
- `--batch-size`: task batch size per future to reduce scheduler overhead.
- `--auto-profile`: scans candidate process/thread/batch combinations and selects a best profile.
- `--profile-processes`, `--profile-threads`, `--profile-batches`: define candidate matrices.
- `--profile-total`, `--profile-runs`, `--final-runs`: control scan and final measurement workload.

Related suites and options:

- `--suite stress` for stress throughput validation.
- `--suite compare` for backend comparisons with measured runs.
- `--suite full_load` for profile-driven full-load runs.
- `--component-processes` for component tests in separate OS processes.

Reference paths:

- `src/opensynaptic/CLI/app.py`
- `src/opensynaptic/services/test_plugin/stress_tests.py`

---

## RS Core (rscore) Updates

This release documents the RS core workflow end-to-end:

- Build Rust core shared library:
  - `os-node rscore-build`
  - or `python -u src/main.py rscore-build`
- Check RS core runtime availability:
  - `os-node rscore-check`
  - or `python -u src/main.py rscore-check`
- Switch backend explicitly:
  - `os-node core --set rscore`
  - optionally persist with `--persist` to `engine_settings.core_backend`
- Include RS build in native C build flow:
  - `python -u src/main.py native-build --include-rscore`

`rscore-check` reports:

- Rust DLL load state
- resolved DLL path and existence
- cargo availability
- active core and available cores

Behavior note:

- If RS native DLL is unavailable, runtime can remain on `pycore`.
- `--require-rust` in test flows can enforce hard failure when RS native path is not usable.

Reference paths:

- `src/opensynaptic/core/rscore/build_rscore.py`
- `src/opensynaptic/CLI/app.py`
- `docs/RSCORE_API.md`
- `docs/PYCORE_RUST_API.md`

---

## Breaking Changes

- None.

No protocol wire-format, packet schema, or required config key removals in this release.

---

## Migration Guide

No mandatory runtime migration.

Recommended actions:

1. Keep `engine_settings.core_backend` explicit (`pycore` or `rscore`) in `Config.json`.
2. For RS deployments, run `rscore-build` and verify with `rscore-check` before switching core.
3. For throughput tuning, run stress tests with `--auto-profile` and persist selected concurrency settings in your CI docs.

---

## Verification

Suggested quick verification commands:

```powershell
python -u src/main.py rscore-check
python -u src/main.py plugin-test --suite stress --workers 8 --total 200 --processes 2 --threads-per-process 4
python -u src/main.py plugin-test --suite stress --auto-profile --profile-total 20000 --final-runs 1
python -u src/main.py plugin-test --suite compare --total 200 --runs 1 --warmup 0 --processes 2
```

Optional RS build verification:

```powershell
python -u src/main.py rscore-build
python -u src/main.py core --set rscore --persist
python -u src/main.py rscore-check
```

---

## Known Issues

- IDE static analysis may show stale parse diagnostics after edit collisions until reindex/restart.
- RS native paths depend on local Rust toolchain and compiled shared library presence.
- Performance numbers from multi-process stress can vary significantly by CPU topology and Windows process scheduling.

---

## Changed Docs

- Updated `README.md`
- Updated `docs/README.md`
- Added `docs/releases/v0.1.1.md`

