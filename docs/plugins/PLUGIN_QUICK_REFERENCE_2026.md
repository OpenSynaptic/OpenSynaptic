# PLUGIN QUICK REFERENCE 2026
## Scope
This document is reconstructed as an English-maintained edition based on the current local codebase.
- File: `docs/plugins/PLUGIN_QUICK_REFERENCE_2026.md`
- Refresh date: 2026-04-01
- Focus: Plugin lifecycle, mount/load behavior, CLI integration, and display provider patterns.
## Code Anchors
- `src/opensynaptic/services/service_manager.py` (plugin lifecycle)
- `src/opensynaptic/services/plugin_registry.py` (built-in plugin mapping and defaults)
- `src/opensynaptic/services/display_api.py` (self-discoverable display providers)
- `src/opensynaptic/services/port_forwarder/main.py` (advanced plugin example)
- `src/opensynaptic/services/dependency_manager/main.py` (utility plugin example)
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
