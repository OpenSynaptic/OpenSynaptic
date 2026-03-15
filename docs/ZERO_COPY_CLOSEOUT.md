# Zero-Copy Closeout

## Scope
This closeout captures the current zero-copy state in OpenSynaptic after transport and fusion-path convergence.

Primary files touched in this phase:
- `src/opensynaptic/core/pycore/unified_parser.py`
- `src/opensynaptic/core/pycore/core.py`
- `src/opensynaptic/core/layered_protocol_manager.py`
- `src/opensynaptic/services/transporters/main.py`
- `src/opensynaptic/core/physical_layer/protocols/{rs485,can,lora}.py`
- `src/opensynaptic/utils/security/security_core.py`

## Runtime Policy
- `engine_settings.zero_copy_transport = true` (default behavior) uses bytes-like passthrough with readonly views.
- `engine_settings.zero_copy_transport = false` keeps legacy byte-materialization fallback (`ensure_bytes`) for compatibility rollback.

## What Is Considered Closed
- Transporter manager and layered protocol manager send paths are zero-copy-first.
- Fusion frame build/decode hot paths are memoryview/bytearray-first.
- Secure XOR path supports in-place write (`xor_payload_into`).
- Component tests include bytes-like regression coverage for fusion.

## Residual Copy Boundaries (Expected)
These are not treated as regressions in this closeout:
- Protocol semantic conversions (`str`/JSON/Base64) in encode/decode layers.
- Native boundary safety copies for readonly buffers.
- Kernel/driver-internal copy behavior on socket/hardware send.

## Closeout Validation
Use single-core as baseline:

```powershell
py -3 -u scripts/zero_copy_closeout.py --runs 3 --total 100000 --config Config.json
```

Or run manually:

```powershell
py -3 -u src/main.py plugin-test --suite component
py -3 -u src/main.py plugin-test --suite stress --total 100000 --workers 1 --no-progress
```

## Release Gate Recommendation
- Component suite: PASS
- Stress suite (`workers=1`): no failures, and median PPS within expected operating band
- Keep `zero_copy_transport` rollback available for one release cycle

