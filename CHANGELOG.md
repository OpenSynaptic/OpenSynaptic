# Changelog

All notable changes to this project are documented in this file.

The format follows Keep a Changelog principles and uses semantic version style tags.

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

