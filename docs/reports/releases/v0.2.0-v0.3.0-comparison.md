# OpenSynaptic v0.2.0 to v0.3.0 Comparison Report

This report summarizes the major functional and operational differences between `v0.2.0` and `v0.3.0`.

---

## Executive Summary

`v0.3.0` keeps the existing pipeline model while significantly improving receive capability, ID lifecycle management, and operational documentation depth.

---

## High-Level Metrics

| Metric | v0.2.0 | v0.3.0 | Change |
|---|---:|---:|---|
| Python files (approx.) | 50 | 65 | +15 |
| Documentation files (approx.) | 12 | 19 | +7 |
| Documentation lines (approx.) | 2000 | 2880 | +44% |
| Integration suites | Basic | Expanded | +5 suites |
| Bidirectional driver coverage | 0/10 full | 10/10 full | Complete |
| Redundant drivers | 6 | 0 | Removed |
| Lease policy controls | Limited | Adaptive | Expanded |

---

## Functional Comparison

### Driver and communication model

- `v0.2.0`: send-oriented coverage with incomplete receive paths.
- `v0.3.0`: all targeted transport/physical/application drivers support `listen()`/receive patterns.
- Result: practical request-response and continuous listener workflows become first-class.

### ID and device lifecycle

- `v0.2.0`: no adaptive lease policy.
- `v0.3.0`: ID lease controls include rate-aware shortening, sustained ultra-rate handling, and metrics emission.
- Result: improved behavior in dynamic/high-churn device environments.

### Protocol architecture and cleanup

- Redundant drivers were removed.
- Layer boundaries (`application`, `transport`, `physical`) are clearer.
- Runtime loading and status maps are easier to reason about.

---

## Quality and Operations

### Test and validation

`v0.3.0` adds stronger verification support across:

- capability audits
- integration flows
- stress and compare suites
- deployment readiness checks

### Documentation maturity

`v0.3.0` introduces deeper references and clearer operator guidance for:

- architecture and API
- lease policy tuning
- transporter extension
- stress and release workflows

---

## Upgrade Impact

### Compatibility

- Backward compatibility is preserved for existing `v0.2.0` usage patterns.
- Existing configs generally remain valid; lease-related keys can be added incrementally.

### Migration effort

- Typical upgrade effort remains low for existing deployments.
- Recommended to run deployment verification, capability audit, and stress sanity checks after update.

---

## Recommended Validation Gate

```powershell
python -u verify_deployment.py
python -u scripts/audit_driver_capabilities.py
python -u src/main.py plugin-test --suite stress --workers 8 --total 200
python -u scripts/integration_test.py
```

---

## Conclusions

`v0.3.0` is a practical upgrade for teams that need complete bidirectional protocol behavior and stronger device ID lifecycle controls, while retaining continuity with existing `v0.2.0` integrations.

