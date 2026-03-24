# OpenSynaptic v0.3.0 Release Document Summary

This page is a compact index for `v0.3.0` release materials.

---

## Primary Release Documents

- Detailed release announcement (publish source): `docs/releases/v0.3.0_announcement_en.md`
- Stable index path: `docs/releases/v0.3.0_announcement.md`
- Upgrade guide: `docs/guides/upgrade/v0.3.0.md`
- Version comparison report: `docs/reports/releases/v0.2.0-v0.3.0-comparison.md`

---

## Suggested Reading Order

### Product and stakeholder audience

1. `docs/releases/v0.3.0_announcement_en.md`
2. `docs/reports/releases/v0.2.0-v0.3.0-comparison.md`
3. `docs/guides/upgrade/v0.3.0.md`

### Engineering and operations audience

1. `docs/guides/upgrade/v0.3.0.md`
2. `docs/ID_LEASE_SYSTEM.md`
3. `docs/ID_LEASE_CONFIG_REFERENCE.md`

---

## Validation Shortlist

```powershell
python -u verify_deployment.py
python -u scripts/audit_driver_capabilities.py
python -u scripts/integration_test.py
```

