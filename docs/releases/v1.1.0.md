# OpenSynaptic v1.1.0-rc1 Release Notes

Release date: 2026-04-01  
Release type: Full-scope release candidate (service plugin ecosystem + visualization refactor + documentation engineering + release pipeline consolidation)

---

## TL;DR

v1.1.0-rc1 moves OpenSynaptic toward better extensibility, observability, and operational reliability.

- Introduces a unified `Display API` so TUI and Web can share one display capability model.
- **`Port Forwarder` is added as a brand-new built-in plugin** (new plugin, not an enhancement of an older built-in module).
- Completes a componentized Textual TUI refactor and aligns Web runtime visualization.
- Strengthens CLI/service lifecycle flows, testing paths, and documentation structure.
- Consolidates packaging and release workflows to reduce build divergence.

---

## Version Scope

This release candidate covers three layers:

1. Product layer: new plugin capabilities and expanded visualization pathways.
2. Engineering layer: stronger CLI/testing/release workflows.
3. Knowledge layer: structured documentation reorganization.

This document intentionally excludes temporary artifacts, cache files, intermediate build outputs, and migration noise.

---

## Added

## 1) Display API (Unified display extension surface)

Primary files:

- `src/opensynaptic/services/display_api.py`
- `src/opensynaptic/services/builtin_display_providers.py`
- `src/opensynaptic/services/example_display_plugin.py`
- `src/opensynaptic/services/id_allocator_display_example.py`

What is added:

- Standardized display provider interface (data extraction + JSON/HTML/Text formatting).
- Unified registry for independent plugin display section registration.
- Built-in display sections for identity, config, transport, pipeline, plugins, and database metadata.

Why it matters:

- Plugins can expose self-described display sections without modifying UI core code.
- Reduces duplicated display logic and improves maintainability.

## 2) Port Forwarder (New built-in plugin in v1.1.0-rc1)

New plugin files:

- `src/opensynaptic/services/port_forwarder/__init__.py`
- `src/opensynaptic/services/port_forwarder/main.py`
- `src/opensynaptic/services/port_forwarder/enhanced.py`
- `src/opensynaptic/services/port_forwarder/examples.py`
- `src/opensynaptic/services/port_forwarder/feature_toggle_examples.py`
- `src/opensynaptic/services/port_forwarder/one_to_many_examples.py`

Positioning (important):

- `Port Forwarder` is included in the built-in plugin set for the first time in this release candidate.
- Built-in registration is defined in `src/opensynaptic/services/plugin_registry.py` under `PLUGIN_SPECS['port_forwarder']`.
- Configuration entry is `Config.json` -> `RESOURCES.service_plugins.port_forwarder`.

Core capabilities:

- Dispatch hijacking for protocol/port-level forwarding.
- Rule model supports `from_protocol/from_port -> to_protocol/to_host/to_port`.
- Supports rule sets, priorities, enable/disable controls, and persistence (`rules_file`).
- Integrated with Display API for runtime rule/state visibility.

Default configuration profile:

- `enabled: true`
- `mode: auto`
- `persist_rules: true`
- `rules_file: data/port_forwarder_rules.json`
- `rule_sets: [default]`

## 3) Textual TUI component set

Key files:

- `src/opensynaptic/services/tui/textual_app.py`
- `src/opensynaptic/services/tui/styles.tcss`
- `src/opensynaptic/services/tui/widgets/*`
- `src/opensynaptic/services/tui/TEXTUAL_REFACTOR_README.md`

What is added:

- Panel decomposition (`identity/config/pipeline/transport/plugins/db`).
- Dedicated style layer and cleaner rendering/state update boundaries.
- Better extension points for plugin-driven display sections.

---

## Changed

## 1) Web runtime visualization alignment

Updated files:

- `src/opensynaptic/services/web_user/main.py`
- `src/opensynaptic/services/web_user/handlers.py`
- `src/opensynaptic/services/web_user/templates/index.html`
- `src/opensynaptic/services/web_user/templates/runtime.js`

Change direction:

- Aligns Web output model with Display API.
- Improves consistency of section rendering and runtime state exposure.
- Better plugin/config status presentation coherence.

## 2) CLI, service wiring, and command parsing

Updated files:

- `src/opensynaptic/CLI/app.py`
- `src/opensynaptic/CLI/build_parser.py`
- `src/opensynaptic/CLI/parsers/service.py`
- `src/opensynaptic/CLI/parsers/test.py`
- `src/opensynaptic/services/service_manager.py`
- `src/opensynaptic/services/plugin_registry.py`

Change direction:

- Stronger service plugin command pathways.
- Improved built-in plugin default synchronization behavior.
- Alias normalization support (for example `port-forwarder -> port_forwarder`).

## 3) Test and verification flow hardening

Updated files:

- `src/opensynaptic/services/test_plugin/main.py`
- `src/opensynaptic/services/test_plugin/component_tests.py`
- `src/opensynaptic/services/test_plugin/stress_tests.py`
- `scripts/services_smoke_check.py`
- `scripts/cli_exhaustive_check.py`
- `tests/tui/test_textual_tui.py`
- `tests/unit/test_textual_tui.py`

Change direction:

- Better regression paths for service/CLI/visualization changes.
- Coverage additions for componentized TUI behavior.

## 4) Release and packaging consolidation

Updated files:

- `.github/workflows/release.yml`
- `pyproject.toml`
- Removed `src/opensynaptic/core/rscore/rust/pyproject.toml`

Change direction:

- Root-level `pyproject.toml` now drives mixed-project build configuration.
- Release jobs include stronger field and artifact consistency checks.
- Reduces configuration drift between root and subproject metadata.

---

## Documentation Updates

This update is a structural documentation reorganization, not only content additions:

- Refreshed primary entry docs: `docs/README.md`, `docs/INDEX.md`, `docs/QUICK_START.md`.
- Expanded document domains: `docs/api/`, `docs/architecture/`, `docs/features/`, `docs/plugins/`, `docs/internal/`, `docs/reports/`.
- Added focused docs for Display API, TUI refactor, plugin specs, performance reports, and implementation reports.

Result: easier navigation and lower collaboration overhead for development, QA, and operations.

---

## Compatibility and Breaking Changes

## Breaking Changes

- No protocol wire-format breaking changes are recorded in this release note scope.
- No core configuration key removals are declared.
- No replacement of the main `OpenSynaptic` orchestration entry is declared.

Note: although this release candidate is focused on additive and consolidation work, regression validation is still recommended before production rollout.

---

## Upgrade and Migration Guidance

## 1) Configuration checks

Validate these paths in your effective config:

- `RESOURCES.service_plugins.port_forwarder`
- `RESOURCES.service_plugins.web_user`
- `RESOURCES.service_plugins.tui`
- `engine_settings.core_backend`

## 2) Minimal Port Forwarder readiness checks

Verify:

- `enabled` state matches your deployment plan.
- `mode` (`auto`/`manual`) matches your service startup policy.
- `rules_file` path is writable.
- `rule_sets` exists and has valid structure.

## 3) Display path verification

- Confirm TUI can render each panel section.
- Confirm Web can render runtime and plugin sections.
- Confirm newly registered Display API sections are discoverable.

---

## Recommended Validation Commands

```powershell
python -u src/main.py plugin-test --suite component
python -u src/main.py plugin-test --suite stress --workers 8 --total 200
python -u src/main.py plugin-test --suite compare --total 10000 --workers 8 --processes 2 --threads-per-process 4 --runs 2 --warmup 1
python -u src/main.py native-check
python -u src/main.py native-build
python scripts/services_smoke_check.py
python scripts/cli_exhaustive_check.py
```

---

## Risk Assessment

- Functional risk: medium-low (no declared breaking changes in core protocol path).
- Operational risk: medium (large changes in plugin and visualization composition).
- Release risk: medium-low (stronger build and artifact checks).
- Documentation value: high (significant structural navigation improvement).

---

## Included Scope (Noise-filtered)

- Service layer: Display API, new Port Forwarder plugin, ServiceManager/Registry integration.
- Visualization layer: Textual TUI component refactor, Web display model alignment.
- Tooling: CLI parser/service command updates, smoke and exhaustive checks.
- Testing: stronger test_plugin regression and TUI-focused tests.
- Release engineering: consolidated workflow and packaging configuration.
- Documentation: structured domains and expanded topic-specific guides/reports.

---

## Acknowledgements

v1.1.0-rc1 establishes a stronger plugin and delivery foundation for upcoming protocol and platform iterations.
