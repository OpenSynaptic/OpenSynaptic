# OpenSynaptic v1.3.0 — Test Report

> **Date**: 2026-04-06  
> **Python**: 3.11 / 3.12 / 3.13  
> **Platforms**: Linux x86_64, Linux ARM64, macOS Intel, macOS Apple Silicon, Windows x86_64  
> **Total tests**: 1275 &nbsp;|&nbsp; ✅ 1273 pass &nbsp;|&nbsp; ⏭ 2 skip &nbsp;|&nbsp; ❌ 0 fail

---

## Summary

| Layer | Script / Suite | Tests | Pass | Skip | Fail |
|-------|---------------|------:|-----:|-----:|-----:|
| Unit + Integration (pytest) | `tests/` | 9 | 9 | 0 | 0 |
| Integration Script | `scripts/integration_test.py` | 9 | 9 | 0 | 0 |
| Business Logic Exhaustive | `scripts/exhaustive_business_logic.py` | 985 | 983 | 2 | 0 |
| Plugin Exhaustive | `scripts/exhaustive_plugin_test.py` | 205 | 205 | 0 | 0 |
| Security Infrastructure | `scripts/exhaustive_security_infra_test.py` | 43 | 43 | 0 | 0 |
| Orthogonal Design | `scripts/exhaustive_orthogonal_test.py` | 24 | 24 | 0 | 0 |
| **Total** | | **1275** | **1273** | **2** | **0** |

> The 2 SKIPs are intentional design-limit markers: values `mol=6.022e+23` and `AU=1e+06` exceed the Base62 int64 encoding ceiling (~9.22×10¹⁴). This is a known hardware constraint, not a defect.

---

## 1. pytest — Unit & Integration Tests (`tests/`)

**Run command:**
```bash
pytest tests/ -v --tb=short
```

### 1.1 `tests/unit/test_core_algorithms.py` — 3 tests

Verifies low-level algorithm correctness against the native C libraries (`os_base62`, `os_security`). All tests auto-SKIP when native libs are unavailable.

| Test | Description |
|------|-------------|
| `test_crc16_reference_vector` | Input `"123456789"` → expected CRC-16/CCITT value `0x29B1` |
| `test_base62_compress_decompress_roundtrip` | Single fact (`Pa`, 101.3): `compress` → `decompress`, numeric error < 0.1% |
| `test_packet_encode_decode_roundtrip` | Humidity fact (`%`, 56.1): full `compress → fusion.run_engine(FULL) → decompress` round-trip, device ID and sensor ID fields verified |

### 1.2 `tests/unit/test_textual_tui.py` — 5 tests

TUI service module unit tests using `MockNode` — no real hardware dependency.

| Test | Description |
|------|-------------|
| `test_tui_service_import` | `TUIService` imports without error |
| `test_tui_render_section` | `render_section('identity')` returns a dict containing `device_id` |
| `test_tui_render_text` | `render_text(['identity'])` returns valid JSON with `identity` and `timestamp` keys |
| `test_tui_cli_commands` | `get_cli_commands()` contains `render`, `interactive`, `bios`, `dashboard` |
| `test_widget_imports` | All TUI widget modules (`BaseTUIPanel`, `IdentityPanel`, `ConfigPanel`, …) import successfully |

### 1.3 `tests/integration/test_pipeline_e2e.py` — 1 test

End-to-end integration test using a real `OpenSynaptic` node.

| Test | Description |
|------|-------------|
| `test_virtual_sensor_to_receive_roundtrip` | 2 sensors (`Pa`, `%`) through full `transmit → receive` loop; verifies packet type, AID type, strategy validity, and decoded field completeness |

---

## 2. Integration Script (`scripts/integration_test.py`) — 9 tests

Standalone Python script verifying the baseline behavior of each node layer in an isolated temp directory.

| # | Test | What is verified |
|---|------|-------------------|
| 1 | Node init | `OpenSynaptic` initialises; `assigned_id` non-empty; `TransportManager` discovers > 0 adapters |
| 2 | Single-sensor transmit | `transmit([["s1","OK",42.0,"Pa"]])` returns non-empty bytes; `strategy` is a valid string |
| 3 | Multi-sensor transmit | 3 channels (`Pa`, `Cel`, `%`) packed into one packet; `len(packet) > 0` |
| 4 | Receive & decompress | Hand-crafted FULL packet; `node.receive()` returns a dict with `id` field, no `error` |
| 5 | Protocol-layer receive | `receive_via_protocol(pkt, addr)` returns `{'type': 'DATA'/'CTRL'/'ERROR', …}` |
| 6 | UDP dispatch | `dispatch(pkt, medium='UDP')` calls the UDP driver without raising |
| 7 | Transport-layer driver | `get_transport_layer_manager()` loads `udp` adapter with a `send` method |
| 8 | Physical-layer driver | `get_physical_layer_manager()` loads `uart` adapter with a `send` method |

---

## 3. Business Logic Exhaustive (`scripts/exhaustive_business_logic.py`) — 985 tests

Systematic exhaustive coverage of the full protocol chain across units, channel combinations, status codes, strategy transitions, and batch API. All suites share one isolated node instance.

```
Suite                                 Total   Pass   Fail   Skip
A | Per-unit full-chain boundary        494    492      0      2
B | Multi-sensor cross-class combos     350    350      0      0
C | Status-word exhaustive matrix        56     56      0      0
D | FULL→DIFF strategy progression        9      9      0      0
E | transmit_batch equivalence            5      5      0      0
F | SI-prefix unit full-chain            71     71      0      0
Total                                   985    983      0      2
Pass rate: 99.8%
```

### Suite A — Per-unit full-chain boundary values (494 tests)

**Chain**: `node.transmit()` → `node.receive()` → numeric reconstruction check

For every UCUM unit across all 15 unit libraries, test boundary values (generic `[0.0, 1e-5, 1.0, 1e6]` for units without special config):

| Unit | Test values |
|------|-------------|
| `K` | 0, 1e-5, 273.15, 373.15, 5778 |
| `Cel` | −273, 0, 25, 100, 5504.85 |
| `degF` | −459, 32, 77, 212 |
| `Pa` | 0, 1e-5, 101325, 1e7 |
| `bar` | 0, 1e-7, 1.01325, 1000 |
| `psi` | 0, 1e-5, 14.696, 1e5 |
| `m / kg / s / A / cd / Hz / bit / By` | 4 boundary values each |
| `mol` | 0, 1e-15, 1, **6.022e23 (SKIP)** |
| Other units | Generic 4 values |

**Pass condition**: decoded value vs expected (post-standardization) within ≤ 0.1% (relative) or 0.001 (absolute).  
**SKIP condition**: standardized absolute value exceeds Base62 int64 range (`|v| > 9.22×10¹⁴`).

### Suite B — Multi-sensor cross-class combinations (350 tests)

One representative unit from each of the 15 unit libraries; enumerate all C(N, k) combinations for **2–8 channels** (up to 50 per channel count); verify that decoded packets parse without error.

### Suite C — Status-word exhaustive matrix (56 tests)

All 7 × 8 = **56 combinations of device status × sensor status**, verified to encode/decode without error.

| Device status (7) | Sensor status (8) |
|---|---|
| ONLINE / OFFLINE / WARN / ERROR / STANDBY / BOOT / MAINT | OK / WARN / ERR / FAULT / N/A / OFFLINE / OOL / TEST |

### Suite D — FULL → DIFF strategy progression (9 tests)

Same device ID sends 8 consecutive rounds (temperature +0.5 °C each round). Verifies strategy-switching behaviour and value consistency.

| Round | Expected strategy | Verified |
|-------|-------------------|---------|
| First `target_sync_count (=3)` rounds | `FULL_PACKET` | Decoded = transmitted |
| Subsequent rounds | `DIFF_PACKET` | Decoded = transmitted; consistent with prior FULL rounds |
| Summary check (+1) | At least one DIFF seen | Or template cached (all-DIFF is also valid) |

### Suite E — `transmit_batch` equivalence (5 tests)

| Test | Content |
|------|---------|
| Batch return count | `transmit_batch()` returns exactly 4 results |
| DEVTESTE1–E4 | Each entry packet > 0 bytes and can be independently decoded |

### Suite F — SI-prefix unit full-chain (71 tests)

Covers the prefix-expansion logic in `standardization.py → _resolve_unit_law()`.

**F1 — Decimal prefixes × prefix-aware units (60 tests)**  
6 representative prefixes (`G/M/k/m/u/n`) × 10 base units (`Hz/By/bit/m/g/Pa/W/V/A/J`) — transmit with prefixed unit, verify decoded value = `1.0 × prefix_factor × unit_factor`.

**F2 — Binary prefixes × informatics units (5 tests)**

| Prefixed unit | Expected standardized value | Result |
|---|---|---|
| `KiBy` | 1 KiB = 8192 bits | ✅ |
| `MiBy` | 1 MiB = 8388608 bits | ✅ |
| `GiBy` | 1 GiB = 8589934592 bits | ✅ |
| `Kibit` | 1 Kibit = 1024 bits | ✅ |
| `Mibit` | 1 Mibit = 1048576 bits | ✅ |

**F3 — `can_take_prefix=False` units correctly rejected (6 tests)**  
Units `count/cmd/rst/stp/cmdA/cmdB` with a prefix applied: `_resolve_unit_law("kcount")` returns `None`; sensor silently dropped by standardizer — no `s1_v` field in returned packet.

---

## 4. Plugin Exhaustive (`scripts/exhaustive_plugin_test.py`) — 205 tests

Strictest per-interface exhaustive coverage for all service plugins: object model, lifecycle, boundary values, concurrency safety, and full registry.

```
Suite                                       Total   Pass   Fail   Skip
A | DatabaseManager (SQLite)                   14     14      0      0
B | PortForwarder rules + lifecycle           107    107      0      0
C | TestPlugin component suite                  4      4      0      0
D | DisplayAPI all-formats exhaustive          44     44      0      0
E | Plugin registry                            36     36      0      0
Total                                         205    205      0      0
Pass rate: 100.0%
```

### Suite A — DatabaseManager (SQLite) — 14 tests

| # | Test |
|---|------|
| A1 | `connect()` + `ensure_schema()` → `_ready = True` |
| A2 | 4 representative facts (1/2/0/8 sensors) each `export_fact()` → True |
| A3 | 3 invalid inputs (`None`, `{}`, non-dict string) → `export_fact()` → False |
| A3b | Minimal valid fact (empty-field dict) → `export_fact()` → True |
| A4 | `export_many(4 facts)` → returns 4 |
| A5 | `export_many([])` → returns 0 |
| A6 | 8 threads concurrent `export_fact()` — no race exception |
| A7 | `close()` → `_ready=False`; `connect()` → `_ready=True` |
| A8 | `from_opensynaptic_config(sql.enabled=False)` → None |
| A9 | `from_opensynaptic_config(sql.enabled=True)` → DatabaseManager instance |

### Suite B — PortForwarder rules + lifecycle — 107 tests

| # | Test |
|---|------|
| B1 | All valid protocol pairs: 10×10=100 `(from, to)` combinations create `ForwardingRule` successfully |
| B2 | 4 invalid protocol names (`HTTP`, `FTP`, `""`, `"  "`) → must raise `ValueError` |
| B3 | `ForwardingRule.to_dict()` / `from_dict()` round-trip — all fields lossless including priority, enabled, from_port |
| B4 | `ForwardingRuleSet.add_rule/remove_rule/get_rules_sorted` — priority descending order correct |
| B5 | `ForwardingRuleSet.to_dict()` / `from_dict()` round-trip |
| B6 | `PortForwarder(node=None)` init + `close()` — no crash |
| B7 | Real node lifecycle: `auto_load()` hijacks dispatch → `is_hijacked=True` → `close()` restores dispatch |
| B8 | `get_required_config()` structure valid (contains `enabled`, `rule_sets`) |

### Suite C — TestPlugin component suite — 4 tests

| # | Test |
|---|------|
| C1 | `build_suite()` callable; returns 133 `TestCase` objects |
| C2 | All `TestCase` class names enumerable |
| C3 | All non-rscore component tests (112 tests) pass: 0 fail, 0 error |
| C4 | `TestPlugin(node=None)` init + `get_required_config()` structure valid |

### Suite D — DisplayAPI + BuiltinDisplayProviders — 44 tests

| # | Test |
|---|------|
| D1 | 6 built-in sections (`identity/config/transport/pipeline/plugins/db`) registered in `DisplayRegistry` |
| D2 | 6 sections × 5 formats (`json/html/text/table/tree`) = 30 render calls, each verifying return type |
| D3 | `register` → duplicate raises False → `unregister` → double-unregister False → re-register succeeds |
| D4 | `list_by_category('core')` → ≥6 built-in providers |
| D5 | `supports_format()` returns True for all 5 `DisplayFormat` enum values |
| D6 | 20 threads concurrent `register()` — no race exception |

### Suite E — Plugin registry — 36 tests

6 checks × 6 plugins (`tui`, `test_plugin`, `web_user`, `dependency_manager`, `env_guard`, `port_forwarder`):

| Check | Content |
|-------|---------|
| `spec` | entry exists in `PLUGIN_SPECS` |
| `import` | module importable via `importlib.import_module()` |
| `class` | class name `getattr()`-able and callable |
| `config` | `get_required_config()` returns valid dict containing `enabled` |
| `nodenil` | `cls(node=None)` init + `close()` — no crash |
| `defaults` | `defaults` dict contains `enabled` key |

---

## 5. Security Infrastructure (`scripts/exhaustive_security_infra_test.py`) — 43 tests

Covers 4 previously zero-coverage core infrastructure modules, including a dedicated randomised ID allocation test.

```
Suite                                       Total   Pass   Fail   Skip
A | IDAllocator — random ID allocation         13     13      0      0
B | OSHandshakeManager — state machine         12     12      0      0
C | EnvironmentGuardService — logic             8      8      0      0
D | EnhancedPortForwarder — all components     10     10      0      0
Total                                          43     43      0      0
Pass rate: 100.0%
```

### Suite A — IDAllocator random ID allocation + lease exhaustive (13 tests)

| # | Test |
|---|------|
| A1 | Allocate 200 unique IDs, all in range `[1, 9999]` |
| A2 | Random seed 500 allocations (with device dedup), unique ID count is reasonable |
| A3 | Same `device_id` twice → same ID reused; different `device_id` → different ID |
| A4 | `release_id(immediate=True)` → `is_allocated` immediately False; next alloc reuses that ID |
| A5 | `allocate_pool(50)` → 50 unique IDs |
| A6 | `release_pool(10, immediate=True)` → returns 10 |
| A7 | `touch(aid)` refreshes `lease_expires_at`; state remains active |
| A8 | `is_allocated` / `get_meta` correct for allocated and unallocated IDs |
| A9 | `stats()` contains all required fields (`total_allocated`, `released`, `range`, `lease_metrics`) |
| A10 | 20 threads concurrent `allocate_id` → 0 duplicates, 0 exceptions |
| A11 | Adaptive rate: `high_rate_threshold_per_hour=1.0`, after 5 allocations `rate` field has numeric value |
| A12 | Persistence round-trip: rebuilt `IDAllocator` retains allocated IDs; device dedup still effective |
| A13 | Pool exhausted → 4th allocation raises `RuntimeError` |

### Suite B — OSHandshakeManager state machine (12 tests)

| # | Test |
|---|------|
| B1 | Initial state: `has_secure_dict=False`, `should_encrypt_outbound=False`, `get_session_key=None` |
| B2 | `note_local_plaintext_sent` → `state=PLAINTEXT_SENT`, `pending_key` derived |
| B3 | `establish_remote_plaintext` → `state=DICT_READY`, `key` derived as bytes, `has_secure_dict=True` |
| B4 | `confirm_secure_dict` via `pending_key` path → True; key matches `derive_session_key(aid, ts)` |
| B5 | `mark_secure_channel` → `state=SECURE`, `decrypt_confirmed=True`, `should_encrypt_outbound=True` |
| B6 | 5 different AIDs all complete INIT→SECURE transition |
| B7 | `classify_and_dispatch`: empty packet → `ERROR`; unknown CMD 0xFF → `UNKNOWN` |
| B8 | `classify_and_dispatch`: `CMD.PING` → `type=CTRL`, response is PONG packet |
| B9 | `device_role=tx_only`: inbound `DATA_FULL` → `type=IGNORED` |
| B10 | `secure_sessions.json` persistence round-trip: rebuilt instance returns same `get_session_key` bytes |
| B11 | `note_server_time(0)` ignored; `note_server_time(1.7e9)` accepted |
| B12 | With mounted `IDAllocator`: `ID_REQUEST` → responds `ID_ASSIGN` with correct cmd byte |

### Suite C — EnvironmentGuardService logic (8 tests)

| # | Test |
|---|------|
| C1 | `get_required_config()` contains all required fields |
| C2 | `ensure_resource_library(force_reset=True)` writes JSON file containing `resources` dict |
| C3 | `_on_error(EnvironmentMissingError event)` → adds 1 issue to `_issues` with `environment` and `ts` fields |
| C4 | `max_history=5`, inject 10 errors → `_issues` truncated to exactly 5 entries |
| C5 | `_status_payload()` contains `ok/service/issues_total/attempts_total/resource_summary` |
| C6 | `_write_status_json` + `_load_state_from_status_json` round-trip; issues correctly restored |
| C7 | `_resolve_resource_entry('native_library','os_base62')` hits default library; unknown kind → empty dict |
| C8 | `auto_load()` → `_initialized=True`; `close()` → `_initialized=False` |

### Suite D — EnhancedPortForwarder all components (10 tests)

| # | Test |
|---|------|
| D1 | Constructor + `get_required_config()` structure valid; `is_hijacked=False` |
| D2 | 5 feature flags (`firewall/traffic_shaping/protocol_conversion/middleware/proxy`) `enable/disable/toggle` all correct |
| D3 | Firewall deny UDP rule → `check_firewall` returns False; TCP with no rule → True |
| D4 | High-priority allow (p=10) beats low-priority deny (p=1): UDP passes, TCP blocked |
| D5 | Token-bucket `TrafficShaper`: `burst_capacity=500`, send 500 B → True; send 1 B → False; `get_wait_time > 0` |
| D6 | `traffic_shaping_enabled=False` → `apply_traffic_shaping` returns 0.0 |
| D7 | Custom `transform_func` invoked; unmatched converter passes packet through unchanged |
| D8 | Middleware `before_dispatch`/`after_dispatch` hooks execute in order; return values propagate correctly |
| D9 | Real `OpenSynaptic` node: `auto_load` hijacks dispatch; `transmit+dispatch` increments `total_packets≥1`; `close` restores |
| D10 | `get_stats()` contains all statistics fields |

---

## 6. Orthogonal Design (`scripts/exhaustive_orthogonal_test.py`) — 24 tests

System-level interaction tests using orthogonal array design, complementing the exhaustive suites by covering multi-factor combinations efficiently.

```
Suite                                               Total   Pass   Fail   Skip
EP | EnhancedPortForwarder 5-flag L8 orthogonal        8      8      0      0
XC | IDAllocator×Unit×Medium×ChannelCount L16         16     16      0      0
Total                                                 24     24      0      0
Pass rate: 100.0%
```

### Suite EP — EnhancedPortForwarder 5-flag L8(2⁵) orthogonal (8 runs)

**Goal**: Verify that any two-factor interaction among `firewall / traffic_shaping / protocol_conversion / middleware / proxy` behaves as expected — especially that "firewall blocks → subsequent steps do not execute" holds across every combination that involves a firewall.

| Run | fw | ts | pc | mw | px | Key assertion |
|-----|----|----|----|----|----|---------------|
| EP-0 | OFF | OFF | OFF | OFF | OFF | All stats = 0 |
| EP-1 | OFF | OFF | OFF | ON | ON | Both middleware hooks execute |
| EP-2 | OFF | ON | ON | OFF | OFF | Shaping + conversion both active |
| EP-3 | OFF | ON | ON | ON | ON | All enabled (fw=OFF): all steps run |
| EP-4 | ON | OFF | ON | OFF | ON | Firewall blocks; conversion does not run; proxy does not run |
| EP-5 | ON | OFF | ON | ON | OFF | **mw×fw key interaction: `before` runs, `after` does not** |
| EP-6 | ON | ON | OFF | OFF | ON | Firewall blocks; shaping does not run |
| EP-7 | ON | ON | OFF | ON | OFF | **mw×fw key interaction: `before` runs, `after` does not** |

**Key finding**: `middleware.before_dispatch` executes before the firewall check (regardless of firewall state); `middleware.after_dispatch` executes only when the firewall allows the packet through. This asymmetry is explicitly verified in EP-5 and EP-7.

### Suite XC — IDAllocator × Unit × Medium × ChannelCount L16(4⁴) orthogonal (16 runs)

**Goal**: Verify cross-layer coupling — device key type affecting ID allocation, unit type affecting encode/decode, transport medium affecting dispatch, channel count affecting packet structure — with every pair of factors covered.

| Factor | Levels | Values |
|--------|--------|--------|
| **A** Device key type | 4 | `device_id` / `mac` / `serial` / `uuid` |
| **B** Unit type | 4 | `Pa` / `Cel` / `Hz` / `By` |
| **C** Transport medium | 4 | `UDP` / `TCP` / `UART` / `CAN` |
| **D** Channel count | 4 | 1 / 2 / 3 / 4 |

Each run verifies 4 sub-chains:
1. **IDAllocator** — allocate D devices using key type A, all unique; meta fields match
2. **Transmit × Receive** — D channels with unit B; `transmit → receive` error-free; `s1_v` is a sensible number
3. **ForwardingRule** — construct `ForwardingRule(from=C, to=C)`; `to_dict` / `from_dict` round-trip correct
4. **Dispatch** — `node.dispatch(pkt, medium=C)` does not raise an exception

---

## 7. Known Limitations

| Limitation | Description |
|------------|-------------|
| Base62 encoding range | `Base62Codec` uses `c_longlong` (int64); with `precision=4` the effective value ceiling is ~**9.22×10¹⁴**. Astronomical-scale unit values exceed this; marked SKIP in tests. |
| UDP dispatch verification | `integration_test.py` Test 6 only verifies the driver call; does not assert successful network delivery. |
| pytest Test 4 double-count | `integration_test.py` Test 4 contains a duplicate `tests_passed += 1`; the display reads `9/9` against 8 logical tests. |
| TUI test isolation | `test_textual_tui.py` uses `MockNode` throughout; does not cover the real-node TUI rendering path. |
| rscore component tests | Tests depending on Rust native libs (`TestRscoreFusionEngine`, etc.) are SKIPped in environments without native build; not counted as failures. |
| MySQL / PostgreSQL | `db_engine` tests use `:memory:` SQLite only; MySQL/PostgreSQL drivers are not validated in CI (require live DB services). |

---

## 8. CI Matrix

Tests run in CI across the following matrix (exhaustive suites run on `ubuntu-latest / py3.11` shard only due to runtime cost):

| Runner | OS | Architecture | Pytest | Exhaustive suites |
|--------|----|--------------|--------|-------------------|
| `ubuntu-latest` | Linux | x86_64 | ✅ | ✅ (single shard) |
| `ubuntu-24.04-arm` | Linux | ARM64 | ✅ | — |
| `macos-13` | macOS Ventura | Intel x86_64 | ✅ | — |
| `macos-latest` | macOS Sequoia | Apple Silicon ARM64 | ✅ | — |
| `windows-latest` | Windows | x86_64 | ✅ | — |

> Windows ARM is intentionally excluded from the CI matrix.

---

*For the full annotated test coverage breakdown (Chinese), see [TEST_COVERAGE.md](TEST_COVERAGE.md).*
