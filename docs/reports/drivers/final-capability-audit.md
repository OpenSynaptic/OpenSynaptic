# Final Driver Capability Audit

This report summarizes final capability status across transport, physical, and application drivers.

---

## Result

All targeted drivers provide operational send and receive/listen capabilities in the validated scope.

---

## Coverage

| Driver | Layer | Send | Receive/Listen | Status |
|---|---|---|---|---|
| udp | L4 | Yes | Yes | Complete |
| tcp | L4 | Yes | Yes | Complete |
| quic | L4 | Yes | Yes | Complete |
| iwip | L4 | Yes | Yes | Complete |
| uip | L4 | Yes | Yes | Complete |
| uart | PHY | Yes | Yes | Complete |
| rs485 | PHY | Yes | Yes | Complete |
| can | PHY | Yes | Yes | Complete |
| lora | PHY | Yes | Yes | Complete |
| mqtt | L7 | Yes | Yes | Complete |

---

## Validation Inputs

- `scripts/audit_driver_capabilities.py`
- `scripts/integration_test.py`
- `scripts/test_runtime_invoke.py`

---

## Notes

Use this report with `docs/reports/drivers/bidirectional-capability.md` for implementation detail and operational verification context.

