# Documentation Index Report

Last updated: 2026-04-01 (local workspace)

---

## Purpose

This report summarizes how to navigate the current documentation set after the English normalization and local structure cleanup.

---

## Quick Entry Points

- Documentation hub: `docs/README.md`
- Full index: `docs/INDEX.md`
- Role-based shortcuts: `docs/QUICK_START.md`
- Main project overview: `README.md`
- AI coding guide: `AGENTS.md`

---

## Category Coverage

- Architecture references: `docs/architecture/`
- API references and contracts: `docs/api/` plus root API docs
- Feature guides: `docs/features/`
- Plugin development docs: `docs/plugins/`
- User/operator guides: `docs/guides/`
- Reports and change logs: `docs/reports/`
- Internal maintenance notes: `docs/internal/`
- Release notes: `docs/releases/`

---

## Verification

Use these checks in the local workspace:

```powershell
python -u -c "import pathlib,re;root=pathlib.Path('.');pat=re.compile(r'[\\u4e00-\\u9fff]');print(sum(1 for p in root.rglob('*.md') if '.venv' not in p.parts and '__pycache__' not in p.parts and pat.search(p.read_text(encoding='utf-8',errors='ignore'))))"
python -u src/main.py plugin-test --suite component
python -u src/main.py plugin-test --suite stress --workers 8 --total 200
```

---

## Notes

- This report reflects local files only.
- For source-of-truth behavior, consult `src/opensynaptic/` modules and `Config.json`.


