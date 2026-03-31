# ARCHITECTURE EVOLUTION COMPARISON
## Scope
This document is reconstructed as an English-maintained edition based on the current local codebase.
- File: `docs/architecture/ARCHITECTURE_EVOLUTION_COMPARISON.md`
- Refresh date: 2026-04-01
- Focus: Runtime architecture, backend selection, and pipeline boundaries from current core modules.
## Code Anchors
- `src/opensynaptic/core/pycore/core.py`
- `src/opensynaptic/core/coremanager.py`
- `src/opensynaptic/core/layered_protocol_manager.py`
- `src/opensynaptic/core/rscore/`
- `src/opensynaptic/services/`
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
