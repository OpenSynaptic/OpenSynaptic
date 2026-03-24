# Driver Quick Reference

Canonical path for driver usage guidance and bidirectional communication notes.

For the historical root-level file, see `DRIVER_QUICK_REFERENCE.md`.

---

## Driver Contract

All drivers should expose:

- `send(payload: bytes, config: dict) -> bool`
- optional `listen(config: dict, callback)` for continuous receive workflows

---

## Layer Mapping

- Application (L7): `mqtt`
- Transport (L4): `udp`, `tcp`, `quic`, `iwip`, `uip`
- Physical (PHY): `uart`, `rs485`, `can`, `lora`

---

## Listener Guidelines

- Run listener loops in a background thread/task.
- Keep callback signatures consistent across drivers.
- Normalize adapter keys to lowercase in all config maps.
- Validate with capability audit and integration tests.

---

## Verification Commands

```powershell
python -u scripts/audit_driver_capabilities.py
python -u scripts/integration_test.py
```

