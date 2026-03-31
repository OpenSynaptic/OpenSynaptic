# FEATURE TOGGLE GUIDE
## Scope
This document is reconstructed as an English-maintained edition based on the current local codebase.
- File: `docs/features/FEATURE_TOGGLE_GUIDE.md`
- Refresh date: 2026-04-01
- Focus: Feature behavior and runtime toggles based on current service/core implementation.
## Code Anchors
- `src/opensynaptic/services/port_forwarder/main.py`
- `src/opensynaptic/services/port_forwarder/enhanced.py`
- `src/opensynaptic/core/pycore/transporter_manager.py`
- `src/opensynaptic/core/layered_protocol_manager.py`
- `Config.json` (`RESOURCES.*_status`, `RESOURCES.*_config`)
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
