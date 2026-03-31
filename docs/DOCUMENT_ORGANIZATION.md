# Documentation Organization (2026-04-01)

This file defines the current documentation layout for the local workspace.

## Directory Structure

```text
docs/
├── README.md
├── INDEX.md
├── QUICK_START.md
├── DOCUMENT_ORGANIZATION.md
├── DOCUMENTATION_ORGANIZATION_FINAL.md
│
├── architecture/   # architecture and FFI analysis
├── api/            # API implementation notes
├── features/       # feature guides
├── guides/         # user/operator/developer guides
├── plugins/        # plugin development docs
├── reports/        # reports, progress notes, changelogs
├── internal/       # internal maintenance docs
├── releases/       # release notes and announcements
└── assets/         # images and media assets
```

## Category Purpose

1. `architecture/`: Architecture internals and FFI-related design analysis.
2. `api/`: API implementation reports and API-specific technical notes.
3. `features/`: Feature-focused guides (for example port forwarder variants).
4. `plugins/`: Plugin development specifications, starter kits, and quick references.
5. `guides/`: How-to documents and operational quick references.
6. `reports/`: Historical reports, fix notes, changelogs, and completion summaries.
7. `internal/`: Maintainer-facing process and troubleshooting notes.
8. `releases/`: Public release notes and announcement records.

## How to Use This Layout

1. Start at `docs/README.md` for overview navigation.
2. Use `docs/INDEX.md` for full file discovery.
3. Use `docs/QUICK_START.md` for role-based navigation.
4. Add new docs under the matching category; avoid root-level markdown growth.

## Maintenance Notes

- Keep actively maintained docs in English.
- Prefer links to canonical docs over duplicated content.
- Update indexes when files are added, moved, or removed.

