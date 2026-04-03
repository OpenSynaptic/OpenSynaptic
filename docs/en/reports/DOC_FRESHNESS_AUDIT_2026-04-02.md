# Documentation Freshness Audit (2026-04-02)

## Scope

Checked high-impact entry documentation and startup/runtime command guidance for consistency with current workspace behavior.

## Audit Result

| Area | File | Status | Notes |
|---|---|---|---|
| Project entry | `README.md` | Updated | Added Windows direct-start wrapper and first-run native auto-repair behavior. |
| Docs hub | `docs/README.md` | Updated | Refreshed snapshot date and added validated runtime quick-start pointers. |
| Quick start | `docs/QUICK_START.md` | Updated | Added executable first-start commands and manual fallback for native build issues. |
| CLI reference | `src/opensynaptic/CLI/README.md` | Updated | Clarified Windows shortcut usage and first-run native auto-repair semantics. |

## Potentially Stale But Intentional Content

| Category | Path Pattern | Interpretation |
|---|---|---|
| Release snapshots | `docs/releases/*.md` | Historical records; may contain old command examples by design. |
| Historical reports | `docs/reports/*.md` | Point-in-time implementation notes; not always current runtime guidance. |

Additional observation from workspace scan:

- `python -u src/main.py ...` style examples appear in many docs (200+ matches in broad search).
- These commands remain executable, but for Windows onboarding we now treat `./run-main.cmd ...` as the recommended first-choice path.

## Current Runtime Truth (validated)

1. Direct startup on Windows can use `./run-main.cmd ...` without `Activate.ps1`.
2. First-run startup now auto-attempts native runtime repair when C bindings are missing.
3. Manual fallback remains `os-node native-check` then `os-node native-build`.

## Maintenance Recommendation

1. Keep operational command guidance centralized in `README.md` and `src/opensynaptic/CLI/README.md`.
2. Treat `docs/releases/` and older `docs/reports/` as archival unless explicitly marked as canonical.
3. For future command-path changes, update these four files in one commit: `README.md`, `docs/README.md`, `docs/QUICK_START.md`, `src/opensynaptic/CLI/README.md`.
