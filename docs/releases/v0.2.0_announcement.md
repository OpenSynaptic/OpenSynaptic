# OpenSynaptic v0.2.0 Release Announcement Copy

## Optional Headlines

- OpenSynaptic v0.2.0 Released: Multi-Process Performance Tuning and RS Core Acceleration Upgrades
- OpenSynaptic v0.2.0 Is Live: High-Concurrency Tuning, Rust Core Workflow, and Practical Benchmark Examples

---

## Announcement Body (Ready to Publish)

We are excited to announce **OpenSynaptic v0.2.0**.

This release focuses on three practical outcomes:

1. **Actionable performance optimization**: improved multi-process concurrency guidance for stable high-load throughput.
2. **Clear RS Core (Rust backend) workflow**: build, validate, and switch with an end-to-end operational path.
3. **More useful optimization examples**: complete scenarios for stress runs, auto-profile tuning, backend comparison, and CI safety checks.

### Key Updates

- Multi-process controls: `--processes`, `--threads-per-process`, `--batch-size`
- Auto-tuning controls：`--auto-profile` with `--profile-*` matrix options
- RS Core toolchain: `rscore-build`, `rscore-check`, `core --set rscore --persist`
- Compare workflow: `plugin-test --suite compare` for `pycore`/`rscore` evaluation

### Why Upgrade to v0.2.0

- Faster discovery of machine-specific concurrency settings without repeated manual trial-and-error
- Lower switching cost for Rust backend validation and incremental rollout
- Reproducible benchmark and profiling routines for release gates

---

## Suggested CTA

- Upgrade and run a stress baseline:

```powershell
python -u src/main.py plugin-test --suite stress --total 20000 --workers 16 --processes 4 --threads-per-process 4 --batch-size 64
```

- Run an automatic profile scan:

```powershell
python -u src/main.py plugin-test --suite stress --auto-profile --profile-total 50000 --profile-runs 1 --final-runs 1 --profile-processes 1,2,4,8 --profile-threads 4,8,16 --profile-batches 32,64,128
```

- Build, check, and switch RS core:

```powershell
python -u src/main.py rscore-build
python -u src/main.py rscore-check
python -u src/main.py core --set rscore --persist
```
