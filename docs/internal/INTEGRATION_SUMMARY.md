# OpenSynaptic Integration Summary

## Changes Made

### 1. Performance Stats Logging Interval (60 seconds)
**Files Modified:**
- `src/opensynaptic/core/Receiver.py`
  - Changed default `report_interval_s` from `5.0` to `60.0` in `ReceiverRuntime.__init__()` (line 177)
  - Changed default `report_interval_s` from `5.0` to `60.0` in `main()` function (line 273)

**Result:**
Performance statistics will now be logged once per minute instead of every 5 seconds, reducing log noise.

Example old output:
```
18:05:48 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0...
18:05:53 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0...
18:05:58 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0...
```

Example new output:
```
18:05:45 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0...
18:06:45 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0...
18:07:45 [INFO] OS: Performance stats recv=0 ok=0 fail=0 drop=0...
```

---

### 2. Integrated Test Suites (Into `plugin-test` Command)

#### Files Created:
1. `src/opensynaptic/services/test_plugin/integration_test.py`
   - Moved from `scripts/integration_test.py`
   - Contains 8 integration tests for core functionality
   - Accessible via: `os-cli plugin-test --suite integration`

2. `src/opensynaptic/services/test_plugin/audit_driver_capabilities.py`
   - Moved from `scripts/audit_driver_capabilities.py`
   - Audits send/receive capabilities of all protocol drivers
   - Accessible via: `os-cli plugin-test --suite audit`

#### Files Modified:

1. **`src/opensynaptic/services/test_plugin/main.py`**
   - Added `run_integration()` method to TestPlugin class
   - Added `run_audit()` method to TestPlugin class
   - Added `_integration()` CLI handler in `get_cli_commands()`
   - Added `_audit()` CLI handler in `get_cli_commands()`
   - Both handlers are exposed via the `plugin-test` command dispatcher

2. **`src/opensynaptic/CLI/parsers/test.py`**
   - Updated `--suite` choices to include `'integration'` and `'audit'`
   - Updated help text to list new suites

3. **`src/opensynaptic/CLI/app.py`**
   - Added handling for `'integration'` and `'audit'` suites in plugin-test command (line ~1310)
   - Both suites use empty `extra_args` list (no additional CLI flags)

---

## Usage

### Run Performance Audit
```bash
python -u src/main.py plugin-test --suite audit
```

Output:
```
[L4 Transport]
  ✓ COMPLETE   UDP        Send:✓  Receive:✓
  ✓ COMPLETE   TCP        Send:✓  Receive:✓
  ...
[PHY Physical]
  ✓ COMPLETE   UART       Send:✓  Receive:✓
  ...
[L7 Application]
  ✓ COMPLETE   MQTT       Send:✓  Receive:✓
```

### Run Integration Tests
```bash
python -u src/main.py plugin-test --suite integration
```

Output:
```
[TEST 1] Node initialization with auto-driver discovery
  ✓ PASS: Node initialized, drivers auto-loaded
[TEST 2] Transmit single sensor
  ✓ PASS: Generated 24 byte packet, strategy=FULL
...
RESULTS: 8/8 tests passed
✓ All tests PASSED! System is ready for production.
```

---

## Migration Note

The old scripts remain available in `scripts/` folder:
- `scripts/integration_test.py`
- `scripts/audit_driver_capabilities.py`

These can be removed if desired, as the functionality is now integrated into the main CLI via the plugin-test command.

To use them independently, you can still run:
```bash
python scripts/integration_test.py
python scripts/audit_driver_capabilities.py
```

---

## Benefits

1. **Reduced Log Noise**: Performance stats now appear once per minute instead of every 5 seconds
2. **Unified CLI**: All tests are accessible through a single `plugin-test` command with consistent interface
3. **Modular Testing**: Tests can be run individually or combined with other suites
4. **Better Integration**: Test modules are now properly integrated into the OpenSynaptic service architecture


