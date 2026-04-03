# OpenSynaptic Restart Command Documentation Summary

**Created**: 2026-04-03  
**Status**: Complete

---

## Overview

Successfully integrated comprehensive documentation for the new `os-node restart --graceful` command across the OpenSynaptic documentation structure.

## Files Modified

### 1. **Root Documentation**
- **[README.md](README.md)** (Main Hub)
  - Updated "Command Categories" section to include `restart`
  - Added `restart` command to the "All Commands" table with description
  - Location: Lines 395, 405

### 2. **CLI Documentation**
- **[src/opensynaptic/CLI/README.md](src/opensynaptic/CLI/README.md)** (CLI Reference)
  - Added `restart` to command reference table
  - Added example usage: `python -u src/main.py restart --graceful --timeout 10`
  - Added example with custom host/port parameters
  - Location: Lines 17, 67-68

### 3. **Workspace Instructions**
- **[AGENTS.md](AGENTS.md)** (Workspace Guidelines)
  - Added graceful restart to "Maintenance utilities" section
  - Included dual-terminal workflow notes
  - Location: Lines 103-106

### 4. **Documentation Index**
- **[docs/INDEX.md](https://github.com/OpenSynaptic/OpenSynaptic/wiki/Navigation-EN)** (Documentation Hub)
  - Added new guide file to "Guides" section
  - Location: Line 64

### 5. **New Comprehensive Guide** ✨
- **[docs/guides/RESTART_COMMAND_GUIDE.md](https://github.com/OpenSynaptic/OpenSynaptic/wiki/en-guides-RESTART_COMMAND_GUIDE)** (11,992 bytes)
  - Complete 370+ line reference guide including:
    - **Quick Start**: 3 usage patterns (basic, custom timeout, custom host/port)
    - **How It Works**: Architecture diagram, execution flow, graceful vs. non-graceful comparison
    - **Examples**: Development workflow, stress testing, production auto-restart
    - **Command Reference**: Complete argument table and output formats
    - **Troubleshooting**: Common issues and solutions
    - **Best Practices**: Do's and Don'ts with code examples
    - **Performance Impact**: Overhead analysis and comparison
    - **Integration**: Examples with other commands
    - **FAQ**: Frequently asked questions

## Documentation Structure

```
OpenSynaptic Docs
├── README.md (Updated)
│   └── CLI Quick Reference (Updated)
├── docs/
│   ├── INDEX.md (Updated)
│   └── guides/
│       ├── RESTART_COMMAND_GUIDE.md (NEW)
│       └── ... other guides
├── src/opensynaptic/CLI/
│   └── README.md (Updated)
└── AGENTS.md (Updated)
```

## Key Documentation Content

### Quick Reference Locations

| Need | Location | Link |
|---|---|---|
| Quick start | README.md | Line 405 |
| Full command reference | CLI README | Lines 17-18 |
| Detailed guide | guides/ | RESTART_COMMAND_GUIDE.md |
| Workspace context | AGENTS.md | Lines 103-106 |

### Command Syntax (from README)

```powershell
# Basic: 10-second graceful shutdown (default)
os-node restart --graceful

# Custom timeout
os-node restart --graceful --timeout 5

# With custom server
os-node restart --graceful --timeout 15 --host 192.168.1.100 --port 9090
```

### Aliases (from CLI README)

| Form | Equivalent |
|---|---|
| `os-node restart` | Primary |
| `os-node os-restart` | Main alias |
| `python -u src/main.py restart` | Direct Python call |
| `.\run-main.cmd restart` | Windows wrapper |

## Documentation Quality Checklist

- ✅ Quick reference updated (README.md)
- ✅ CLI reference updated (src/opensynaptic/CLI/README.md)
- ✅ Workspace guidelines updated (AGENTS.md)
- ✅ Documentation index updated (https://github.com/OpenSynaptic/OpenSynaptic/wiki/Navigation-EN)
- ✅ Comprehensive guide created (https://github.com/OpenSynaptic/OpenSynaptic/wiki/en-guides-RESTART_COMMAND_GUIDE)
- ✅ All cross-references valid
- ✅ Examples executable on Windows/Unix
- ✅ Troubleshooting section included
- ✅ Best practices documented
- ✅ Performance analysis provided

## How to Use This Guide

### For Quick Learning
1. Read the summary in [README.md](README.md) line 405
2. Try basic example: `os-node restart --graceful`
3. Check CLI examples in [src/opensynaptic/CLI/README.md](src/opensynaptic/CLI/README.md)

### For Deep Understanding
1. Start with [docs/guides/RESTART_COMMAND_GUIDE.md](https://github.com/OpenSynaptic/OpenSynaptic/wiki/en-guides-RESTART_COMMAND_GUIDE) "Overview" section
2. Review "How It Works" architecture
3. Follow examples in your use case
4. Consult "Troubleshooting" if issues arise

### For Integration with Other Commands
- See "Integration with Other Commands" in RESTART_COMMAND_GUIDE.md
- Examples include: config updates, plugin tests, stress testing

### For Production Deployment
- "Best Practices" section with Do's/Don'ts
- Production auto-restart script example
- Performance impact analysis
- Troubleshooting guide

## Cross-References

All guides properly link to related documents:

```markdown
- [README.md](../../README.md) – CLI Quick Reference
- [src/opensynaptic/CLI/README.md](../../src/opensynaptic/CLI/README.md) – Detailed CLI Examples
- [ARCHITECTURE.md](../ARCHITECTURE.md) – System Architecture
- [CONFIG_SCHEMA.md](../CONFIG_SCHEMA.md) – Configuration Reference
```

## Future Enhancements

Potential additions (not included in this update):

1. **Video tutorial link** (when available)
2. **Metric/monitoring integration** (health check after restart)
3. **Kubernetes/systemd integration** examples
4. **Multi-process restart orchestration**
5. **Graceful shutdown signal handling** (SIGTERM implementation)

## Validation

All documentation has been:
- ✅ Syntactically validated
- ✅ Cross-referenced checked
- ✅ Example code verified
- ✅ Markdown formatting checked
- ✅ Line breaks and spacing consistent with existing docs

## File Locations

```
e:\新建文件夹 (2)\
├── README.md (2 lines modified at 395, 405)
├── AGENTS.md (4 lines modified at 103-106)
├── docs/
│   ├── INDEX.md (1 line added at 64)
│   └── guides/
│       └── RESTART_COMMAND_GUIDE.md (NEW, 370+ lines)
└── src/opensynaptic/CLI/
    └── README.md (2 lines modified at 17, 67-68)
```

---

## Summary

The `os-node restart --graceful` command is now fully documented across:
- Main README (quick reference)
- CLI README (examples)
- Workspace guidelines (context)
- New comprehensive guide (deep reference)
- Documentation index (for discovery)

Users can now find help at any level of detail they need, from a one-line summary to a 370-line reference guide.
