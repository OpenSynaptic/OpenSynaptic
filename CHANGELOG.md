# Changelog

All notable changes to this project are documented in this file.

The format follows Keep a Changelog principles and uses semantic version style tags.

---

## [0.3.0] - 2026-03-25

### Added

- Added install-and-run onboarding flow centered on `os-node demo`.
- Added user-scoped default config path support: `~/.config/opensynaptic/Config.json`.
- Added first-run wizard controls via global CLI flags: `--yes` and `--no-wizard`.
- Added richer demo behavior: virtual temperature/humidity/pressure sensors, optional browser auto-open, loopback Web UI startup, and graceful Ctrl+C exit.
- Added `argcomplete`-powered CLI completion for command names and argument values.
- Added dynamic completion for `config-get --key` / `config-set --key` (nested dot paths + list indexes) with short-lived cache.
- Added dynamic transporter completion for medium/name fields across CLI commands.
- Added plugin completion routing for `plugin-cmd --plugin` and plugin subcommands.
- Added interactive `wizard` / `init` command to generate config by Q&A (`--default` for one-shot defaults).
- Added `repair-config` flow improvements for loopback bootstrap and migration-safe default injection.
- Added post-install welcome banner in `setup.py` install/develop flows with quick next-step commands and support links.
- Added demo visual asset `docs/assets/demo_quickstart.svg` and top-level README quickstart section.
- Added completion activation helper script `scripts/enable_argcomplete.ps1`.
- Added humidity UCUM unit definition (`%`) in `libraries/Units/Opensynaptic_Ucum_Humidity.json` and synced symbol output for standardization/compression lookup.
- Added repository `LICENSE` (MIT) and expanded `.gitignore` coverage for Python/Rust wheel build artifacts.
- Added Rust wheel packaging scaffold for `rscore` (`src/opensynaptic/core/rscore/rust/pyproject.toml`, maturin metadata, and PyO3 module entrypoint) while preserving existing C-ABI exports.
- Added CI workflows under `.github/workflows/` for matrix test/build and tag-driven release publish.
- Added baseline test suite under `tests/` with unit checks (Base62/CRC/packet encode-decode) and integration roundtrip coverage.

### Changed

- `OpenSynaptic` config bootstrap now auto-creates missing config files and performs version-aware default merge migration.
- CLI runtime now auto-bootstraps config for first-time users and can route directly into demo mode on first launch.
- Synced root `AGENTS.md` guidance with current CLI/core workflows, plugin-test suites, and runtime reporting conventions.
- Updated project metadata in `pyproject.toml` (version, readme/license metadata, Python version requirement, classifiers, dev/release extras, pytest/coverage config).
- Updated root `README.md` demo image reference to an absolute GitHub URL for PyPI markdown rendering compatibility.

### Fixed

- Fixed legacy static-analysis warnings in `src/opensynaptic/CLI/app.py`:
  - removed unused import (`CLI_HELP_TABLE`)
  - normalized callable bool return in `_node_id_is_missing`
  - ensured `sensors` is initialized before use in transmit path
- Improved CLI exception translation for common operator-facing failures (for example CRC/data-integrity and missing-ID startup issues) with actionable next-step hints.

---

## [0.2.0] - 2026-03-16

### Added

- Added release note `docs/releases/v0.2.0.md` with a performance optimization focus.
- Added optimized usage examples for multi-process stress, auto-profile tuning, backend comparison, and RS core switching.
- Added announcement template `docs/releases/v0.2.0_announcement.md` for external release communication.

### Changed

- Updated release entry points in `README.md` and `docs/README.md` to point to `v0.2.0`.
- Expanded documented guidance for high-load test parameters (`--processes`, `--threads-per-process`, `--batch-size`, `--auto-profile`).
- Expanded RS core operational guidance (`rscore-build`, `rscore-check`, `core --set rscore --persist`, `native-build --include-rscore`).

### Notes

- `v0.2.0` focuses on performance optimization guidance and operations clarity.
- No protocol wire-format breaking change is declared in this release.

---

## [0.1.1] - 2026-03-16

### Added

- Added release note `docs/releases/v0.1.1.md` with consolidated guidance for multi-process stress tuning and RS core operations.
- Added explicit documentation references for RS core commands (`rscore-build`, `rscore-check`) and backend selection (`core --set rscore`).

### Changed

- Updated release entry points in `README.md` and `docs/README.md` to point to `v0.1.1`.
- Clarified concurrency options for test workflows (`--processes`, `--threads-per-process`, `--auto-profile`, profile candidate matrix flags).

### Notes

- No protocol wire-format changes are declared for `v0.1.1`.

---

## [1.1.0] - 2026-03-16 (Draft)

### Added

- Added documentation hub at `docs/README.md`.
- Added architecture reference at `docs/ARCHITECTURE.md` with pipeline, layer model, ID lifecycle, and native dependency notes.
- Added release note draft at `docs/releases/v1.1.0.md`.

### Changed

- Updated top-level `README.md` with centralized documentation and release-note entry points.
- Clarified release workflow by introducing a project-level changelog.

### Fixed

- Documentation discoverability and onboarding flow for new contributors.

### Notes

- This is a documentation-focused release draft; no protocol payload format or runtime behavior changes are declared in this entry.
