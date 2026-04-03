# Contributing to OpenSynaptic

Thank you for your interest in contributing to OpenSynaptic.

This project is a high-performance IoT protocol stack focused on:
- UCUM standardization
- Base62 compression
- Binary packet fusion (FULL and DIFF)
- Pluggable transport layers

## Ways to Contribute

You can help by:
- Reporting bugs
- Proposing features
- Improving documentation
- Submitting code fixes and tests
- Reviewing pull requests

## Before You Start

1. Search existing issues and pull requests first.
2. For large changes, open an issue to discuss design and scope.
3. Keep changes focused. Avoid mixing unrelated refactors with bug fixes.

## Development Setup

### Prerequisites

- Python 3.11+
- Optional: Rust toolchain for rscore-related work

### Install

```powershell
pip install -e .
```

Windows wrappers (no Activate.ps1 required):

```powershell
.\scripts\venv-python.cmd -m pip install -e .[dev]
.\run-main.cmd --help
```

## Project Conventions

Please follow these repository-specific rules:

- Import public core symbols from opensynaptic.core unless you are intentionally editing backend internals.
- Transporter keys in config and status maps must be lowercase (udp, tcp, mqtt, uart, etc.).
- assigned_id == 4294967295 is a sentinel for unassigned and must not be used as a real device id.
- Keep layer maps consistent:
  - application_status / application_config
  - transport_status / transport_config
  - physical_status / physical_config
- Service plugins should follow ServiceManager lifecycle:
  - __init__
  - get_required_config
  - auto_load
  - optional close

If you edit unit definitions under libraries/Units, regenerate symbols:

```powershell
python -c "from libraries.harvester import SymbolHarvester; SymbolHarvester().sync()"
```

## Testing

Run relevant tests before opening a PR.

### Minimum local checks

```powershell
python scripts/integration_test.py
python scripts/udp_receive_test.py --protocol udp --host 127.0.0.1 --port 8080 --config Config.json
py -3 -m pytest --cov=opensynaptic tests
```

### Recommended extra checks

```powershell
python scripts/audit_driver_capabilities.py
python scripts/cli_exhaustive_check.py
python scripts/services_smoke_check.py
```

For transporter or protocol changes, run protocol matrix and related script checks.

## Branches and Commits

- Branch from main for normal feature and bugfix work.
- Use clear commit messages.
- Keep each commit logical and reviewable.

Recommended format:

- feat: add xyz
- fix: correct abc
- docs: update guide
- test: add coverage for def
- refactor: simplify ghi

## Pull Request Guidelines

A good pull request should include:

1. Clear summary of what changed and why.
2. Linked issue number when applicable.
3. Test evidence (commands and key output).
4. Notes on backward compatibility and config impact.
5. Documentation updates if behavior changes.

### PR checklist

- [ ] Code follows repository conventions
- [ ] Tests added or updated for new behavior
- [ ] Local verification completed
- [ ] Docs updated where needed
- [ ] No unrelated file churn

## Documentation Changes

When changing behavior, update the relevant documentation under docs/.
Prefer linking to canonical docs rather than duplicating large sections.

## Security-Sensitive Changes

For security-related fixes, follow SECURITY.md and avoid public disclosure until a fix is ready.

## License

By contributing, you agree that your contributions are licensed under the same license as this repository.
