# OpenSynaptic Workspace Instructions

This repository uses `AGENTS.md` as the single workspace-wide instruction file.
Do not maintain a parallel `.github/copilot-instructions.md` for the same scope.

## Project Snapshot

OpenSynaptic is a 2-N-2 IoT protocol stack:

1. Standardize sensor facts to UCUM
2. Compress with Base62
3. Fuse into binary packet (FULL/DIFF)
4. Dispatch over pluggable transporters

Pipeline entry points:

```text
sensors
  -> OpenSynapticStandardizer.standardize()
  -> OpenSynapticEngine.compress()
  -> OSVisualFusionEngine.run_engine()
  -> OpenSynaptic.dispatch()
```

## Architecture Boundaries

- Core facade and backend selection: `src/opensynaptic/core/__init__.py`, `src/opensynaptic/core/coremanager.py`
- Python core orchestrator: `src/opensynaptic/core/pycore/core.py`
- Three-layer transport:
  - L7 app drivers: `src/opensynaptic/services/transporters/drivers/`
  - L4 transport: `src/opensynaptic/core/transport_layer/protocols/`
  - PHY: `src/opensynaptic/core/physical_layer/protocols/`
- Service/plugin lifecycle hub: `src/opensynaptic/services/service_manager.py`
- ID lease allocator: `plugins/id_allocator.py`
- Unit symbol generation: `libraries/harvester.py`

## Build And Test Commands

Install and smoke run:

```powershell
pip install -e .
os-node demo --open-browser
```

Windows wrappers (no Activate.ps1 required):

```powershell
.\run-main.cmd demo --open-browser
.\scripts\venv-python.cmd -m pip install -e .[dev]
```

Core verification:

```powershell
python scripts/integration_test.py
python scripts/udp_receive_test.py --protocol udp --host 127.0.0.1 --port 8080 --config Config.json
py -3 -m pytest --cov=opensynaptic tests
```

Plugin and stress suites:

```powershell
python -u src/main.py plugin-test --suite component
python -u src/main.py plugin-test --suite stress --workers 8 --total 200
python -u src/main.py plugin-test --suite integration
python -u src/main.py plugin-test --suite audit
```

Native and Rust backend:

```powershell
python -u src/main.py native-check
python -u src/main.py native-build
python -u src/main.py rscore-check
python -u src/main.py rscore-build
python -u src/main.py core --set rscore --persist
```

Maintenance utilities:

```powershell
python scripts/audit_driver_capabilities.py
python scripts/cli_exhaustive_check.py
python -c "from libraries.harvester import SymbolHarvester; SymbolHarvester().sync()"

# Graceful restart (dual-terminal workflow)
# Terminal A: os-node run
# Terminal B: os-node restart --graceful --timeout 10
```

## Project-Specific Conventions

- Import public core symbols from `opensynaptic.core` unless you are intentionally editing backend internals.
- Core backend precedence is:
  1. `OPENSYNAPTIC_CORE` env var
  2. `engine_settings.core_backend` in config
  3. `pycore` fallback
- `assigned_id == 4294967295` (`MAX_UINT32`) means unassigned. Never use it as a real device id.
- Runtime default config path is user-level `~/.config/opensynaptic/Config.json`; repo `Config.json` is the bootstrap template.
- Transporter keys in all status/config maps must be lowercase (`udp`, `mqtt`, `uart`).
- Keep layer-specific maps (`application_*`, `transport_*`, `physical_*`) consistent; legacy `transporters_status` remains a merged mirror.
- Service plugins should follow lifecycle contract in `ServiceManager`: `__init__`, `get_required_config`, `auto_load`, optional `close` and CLI helpers.
- If you edit `libraries/Units/*.json`, run `SymbolHarvester().sync()` to refresh `libraries/OS_Symbols.json`.
- Base62/security paths rely on native bindings (`src/opensynaptic/utils/c/native_loader.py`); there is no pure-Python fallback for those code paths.

## Common Pitfalls

- On Windows paths containing parentheses, avoid fragile `if (...)` blocks in `.cmd` wrappers.
- `transmit_batch` timer behavior on Windows can inflate single-packet wall latency; disable batch mode for low-latency one-off sends.
- `plugins/` is outside `src/`; script-style entrypoints should bootstrap `sys.path` like `scripts/integration_test.py` when needed.

## Documentation Map (Link, Do Not Embed)

Start here:

- `README.md`
- `docs/INDEX.md`
- `docs/README.md`

Core references:

- Architecture: `docs/ARCHITECTURE.md`
- Configuration schema: `docs/CONFIG_SCHEMA.md`
- API overview: `docs/API.md`
- Core API details: `docs/CORE_API.md`
- Pycore/Rust interface: `docs/PYCORE_RUST_API.md`, `docs/RSCORE_API.md`

Feature guides:

- ID lease system: `docs/ID_LEASE_SYSTEM.md`
- ID lease config quick reference: `docs/ID_LEASE_CONFIG_REFERENCE.md`
- Transporter plugin guide: `docs/TRANSPORTER_PLUGIN.md`
- Display API guide: `docs/guides/DISPLAY_API_GUIDE.md`

Plugin development:

- Starter kit: `docs/plugins/PLUGIN_STARTER_KIT.md`
- Full specification: `docs/plugins/PLUGIN_DEVELOPMENT_SPECIFICATION_2026.md`

## Instruction Layering

- Root defaults live in this file.
- For docs-only maintenance flows, follow `docs/internal/AGENTS.md` when working under `docs/internal/`.
- If the repo grows, prefer additional scoped `AGENTS.md` files in subdirectories over expanding this root file into a kitchen sink.
