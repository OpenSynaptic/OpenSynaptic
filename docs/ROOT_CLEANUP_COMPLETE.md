# Root Documentation Cleanup Report

**Report date**: 2026-04-01  
**Scope**: local workspace only

---

## Current Result

- Root markdown files: **2** (`README.md`, `AGENTS.md`)
- Markdown files under `docs/`: **98**
- Markdown files in repository (excluding `.venv`): **111**

This confirms that markdown documentation is centralized under `docs/` and root-level markdown remains minimal.

---

## Root vs Docs Layout

### Repository root (markdown)

- `README.md`
- `AGENTS.md`

### `docs/` categories

- `architecture/` (4)
- `api/` (2)
- `features/` (5)
- `guides/` (10)
- `plugins/` (10)
- `reports/` (31)
- `internal/` (12)
- `releases/` (8)

---

## Why This Structure Helps

- Keeps root clean for project-level entry points.
- Makes docs discoverable by topic category.
- Simplifies maintenance and indexing.

---

## Maintainer Guidance

1. Add new documentation under `docs/` only.
2. Keep root markdown limited to `README.md` and `AGENTS.md`.
3. Update `docs/INDEX.md` and `docs/README.md` when structure changes.
4. Keep maintained docs in English.

