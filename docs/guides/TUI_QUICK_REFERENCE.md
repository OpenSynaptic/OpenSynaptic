# TUI QUICK REFERENCE
## Scope
This document is reconstructed as an English-maintained edition based on the current local codebase.
- File: `docs/guides/TUI_QUICK_REFERENCE.md`
- Refresh date: 2026-04-01
- Focus: Operator/developer workflows and command-level usage from current CLI and service code.
## Code Anchors
- `src/opensynaptic/main.py`
- `src/opensynaptic/CLI/build_parser.py`
- `src/opensynaptic/CLI/parsers/`
- `src/opensynaptic/services/tui/`
- `src/opensynaptic/services/web_user/`
## Practical Verification
Use these commands to verify related behavior in the current workspace:
```powershell
pip install -e .
python -u src/main.py plugin-test --suite component
python -u src/main.py plugin-test --suite stress --workers 8 --total 200
```
## Related Documentation
- `docs/README.md`
- `docs/INDEX.md`
- `docs/QUICK_START.md`
- `AGENTS.md`
- `README.md`
## Notes
- This page is normalized to English and aligned with current local paths.
- For canonical runtime behavior, prefer source modules in `src/opensynaptic/`.
