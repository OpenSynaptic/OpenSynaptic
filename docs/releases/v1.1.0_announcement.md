# OpenSynaptic v1.1.0-rc1 Public Announcement

OpenSynaptic v1.1.0-rc1 is now available.

This release candidate focuses on engineering maturity and extensibility. It delivers coordinated upgrades across the service plugin ecosystem, visualization experience, test flows, and release pipeline. For teams rolling out IoT workloads, v1.1.0-rc1 aims to make the stack easier to extend, easier to observe, and easier to ship reliably.

## Highlights

- Introduces a unified `Display API` so TUI and Web share one display capability model.
- **`Port Forwarder` debuts as a brand-new built-in service plugin**, enabling rule-based protocol/port forwarding and runtime visibility.
- TUI completes a Textual component refactor, and the Web console is aligned with the new display model.
- CLI, service lifecycle tooling, tests, and documentation are strengthened together.
- Release and packaging workflows are further consolidated for consistency.

## Important Note: Port Forwarder Is New in This Release

`Port Forwarder` enters the built-in plugin set for the first time in v1.1.0-rc1 (not an enhancement of an older built-in module).

- Plugin registration: `src/opensynaptic/services/plugin_registry.py` (`PLUGIN_SPECS['port_forwarder']`)
- Config entry: `Config.json` -> `RESOURCES.service_plugins.port_forwarder`
- Default capabilities include rule sets, enable/disable controls, and rule persistence (`rules_file`)

## Recommended Upgrade Actions (Minimal)

1. Verify `RESOURCES.service_plugins.port_forwarder`, `RESOURCES.service_plugins.web_user`, and `RESOURCES.service_plugins.tui` in your config.
2. Run service smoke checks and plugin tests before production rollout.
3. Start with default Port Forwarder rule sets, then introduce custom rules incrementally.

## Documentation

- Full release notes: `docs/releases/v1.1.0.md`
- Documentation index: `docs/INDEX.md`

Feedback from real deployments is welcome.
