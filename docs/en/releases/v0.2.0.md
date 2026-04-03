# OpenSynaptic v0.2.0 Release Notes

Release date: 2026-03-16  
Type: Performance optimization + multi-process and RS core workflow enhancement

---

## Highlights

- Upgraded release line to `v0.2.0` with a clear performance-focused narrative.
- Consolidated multi-process stress tuning, profile scanning, and RS core operation guidance.
- Added optimized usage examples for high-load validation and backend switching.
- Kept compatibility with existing protocol wire format and configuration structure.

---

## Performance Optimizations

This release emphasizes practical throughput and runtime efficiency improvements:

- Multi-process stress concurrency is now explicitly documented for production-like benchmarking.
- Auto-profiling workflow (`--auto-profile`) is highlighted for selecting process/thread/batch combinations.
- Scheduler overhead tuning guidance is added through `--batch-size` and profile candidate matrices.
- RS core path (`rscore`) usage is clarified for native acceleration and backend comparability.

Key optimization controls:

- `--processes`
- `--threads-per-process`
- `--batch-size`
- `--auto-profile`
- `--profile-processes`, `--profile-threads`, `--profile-batches`
- `--profile-total`, `--profile-runs`, `--final-runs`

---

## Optimized Usage Examples

### 1) High-throughput multi-process stress

```powershell
python -u src/main.py plugin-test --suite stress --total 20000 --workers 16 --processes 4 --threads-per-process 4 --batch-size 64
```

### 2) Auto-profile best concurrency matrix

```powershell
python -u src/main.py plugin-test --suite stress --auto-profile --profile-total 50000 --profile-runs 1 --final-runs 1 --profile-processes 1,2,4,8 --profile-threads 4,8,16 --profile-batches 32,64,128
```

### 3) Compare pycore vs rscore under controlled load

```powershell
python -u src/main.py plugin-test --suite compare --total 10000 --workers 8 --processes 2 --threads-per-process 4 --runs 2 --warmup 1
```

### 4) Build and switch to RS core for accelerated path

```powershell
python -u src/main.py rscore-build
python -u src/main.py rscore-check
python -u src/main.py core --set rscore --persist
```

### 5) Enforce RS-native path in CI

```powershell
python -u src/main.py plugin-test --suite stress --total 5000 --workers 8 --processes 2 --require-rust
```

---

## RS Core (rscore) Notes

- Build: `os-node rscore-build` / `python -u src/main.py rscore-build`
- Check: `os-node rscore-check` / `python -u src/main.py rscore-check`
- Switch: `os-node core --set rscore [--persist]`
- Integrated native build: `python -u src/main.py native-build --include-rscore`

`rscore-check` exposes runtime readiness details:

- RS DLL load state
- DLL path and existence
- cargo availability
- active core and available cores

If RS DLL is not available, runtime can stay on `pycore`; test flows can enforce RS requirement via `--require-rust`.

---

## Breaking Changes

- None.

No protocol packet schema or required config key removals are introduced in `v0.2.0`.

---

## Migration Guide

No mandatory migration is required.

Recommended upgrade actions:

1. Pin `engine_settings.core_backend` explicitly to `pycore` or `rscore` in `Config.json`.
2. For RS deployments, execute `rscore-build` then verify with `rscore-check` before switching backend.
3. For performance-sensitive environments, run one `--auto-profile` pass per hardware class and preserve the selected parameters in CI/CD docs.

---

## Verification

```powershell
python -u src/main.py rscore-check
python -u src/main.py plugin-test --suite stress --total 5000 --workers 8 --processes 2 --threads-per-process 4 --batch-size 64
python -u src/main.py plugin-test --suite stress --auto-profile --profile-total 20000 --final-runs 1
python -u src/main.py plugin-test --suite compare --total 5000 --runs 1 --warmup 0 --processes 2
```

Optional extended verification:

```powershell
python -u src/main.py native-check
python -u src/main.py native-build --include-rscore
python -u src/main.py core --set rscore --persist
python -u src/main.py plugin-test --suite all --workers 8 --total 200
```

---

## Known Issues

- IDE/static analysis may show stale parse diagnostics after edit collisions until language service reindex/restart.
- RS native path depends on local Rust toolchain and built shared library availability.
- Multi-process benchmark results vary by CPU topology, process affinity, and Windows scheduler behavior.

---

## Docs Updated

- Updated `README.md`
- Updated `docs/README.md`
- Updated `CHANGELOG.md`
- Added `docs/releases/v0.2.0.md`

