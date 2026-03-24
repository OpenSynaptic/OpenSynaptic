# OpenSynaptic v0.3.0 Upgrade Guide

This guide covers migration from `v0.2.0` to `v0.3.0`.

- Estimated time: 15-30 minutes
- Compatibility: backward compatible for existing core workflows
- Audience: operators, backend engineers, and release maintainers

---

## Quick Start (5 Minutes)

### Option A: Upgrade existing deployment (recommended)

```powershell
cd .
git pull origin main
python -u verify_deployment.py
python -u src/main.py plugin-test --suite stress --total 5000 --workers 8
```

### Option B: Fresh setup

```powershell
cd .
pip install -e .
python -u verify_deployment.py
python -u test_id_lease_system.py
```

---

## Full Procedure

### 1) Prepare

```powershell
python -u src/main.py --version
Copy-Item Config.json Config.json.backup
```

### 2) Update code

```powershell
git pull origin main
```

If you cannot use Git, copy updated files manually, including `docs/`, `scripts/`, `README.md`, `CHANGELOG.md`, and `AGENTS.md`.

### 3) Verify deployment

```powershell
python -u verify_deployment.py
```

Expected result: deployment checks pass and environment is ready.

### 4) Validate ID lease behavior (recommended)

```powershell
python -u test_id_lease_system.py
```

### 5) Audit driver capability

```powershell
python -u scripts/audit_driver_capabilities.py
```

Expected result: all target drivers report complete send + receive/listen support.

### 6) Run performance sanity check

```powershell
python -u src/main.py plugin-test --suite stress --total 10000 --workers 8 --processes 2 --threads-per-process 4 --batch-size 64
```

Compare throughput and tail latency with your previous baseline.

---

## Configuration Notes

Use `security_settings.id_lease` in `Config.json` for lease policy tuning.

Reference docs:

- `docs/ID_LEASE_SYSTEM.md`
- `docs/ID_LEASE_CONFIG_REFERENCE.md`

Example baseline:

```json
{
  "security_settings": {
    "id_lease": {
      "offline_hold_days": 30,
      "base_lease_seconds": 2592000,
      "min_lease_seconds": 0,
      "rate_window_seconds": 3600,
      "high_rate_threshold_per_hour": 60,
      "ultra_rate_threshold_per_hour": 180,
      "ultra_rate_sustain_seconds": 600,
      "high_rate_min_factor": 0.2,
      "adaptive_enabled": true,
      "ultra_force_release": true,
      "metrics_emit_interval_seconds": 5
    }
  }
}
```

---

## Upgrade Checklist

- [ ] Code updated to v0.3.0
- [ ] `verify_deployment.py` passed
- [ ] ID lease tests passed
- [ ] Driver capability audit passed
- [ ] Stress sanity run completed without regressions
- [ ] `Config.json` backup retained

---

## Troubleshooting

### Missing documentation file

If a docs file is missing, resync repository files and verify the `docs/` tree.

### Import errors after upgrade

```powershell
pip install -e .
```

### Corrupted ID allocation file

```powershell
Remove-Item data/id_allocation.json
python -u test_id_lease_system.py
```

### Version mismatch

```powershell
python -u -c "from opensynaptic import __version__; print(__version__)"
```

---

## Next Steps

1. Read `docs/ID_LEASE_SYSTEM.md` for lifecycle details.
2. Run `scripts/integration_test.py` for integration confidence.
3. Review `docs/guides/drivers/quick-reference.md` for listen/send patterns.
4. Track stress metrics (`p95`, `p99`, `p99.9`) in your release gate.

