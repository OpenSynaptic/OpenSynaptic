# OpenSynaptic Textual TUI Refactor

## Overview

The OpenSynaptic TUI has been refactored to use the **Textual** framework, a modern Python library for building sophisticated terminal user interfaces. The new implementation provides:

- **Rich interactive dashboard** with sections for identity, config, transport, pipeline, plugins, and database
- **Keyboard-driven navigation** with intuitive shortcuts
- **Real-time data refresh** with configurable intervals
- **JSON view modal** for detailed data inspection
- **Graceful fallback** to BIOS mode if Textual is not available

## Installation

To use the new Textual-based TUI, install with the optional `tui` dependency:

```bash
pip install opensynaptic[tui]
```

Or install Textual separately:

```bash
pip install textual>=0.40.0
```

## Usage

### Interactive Dashboard (Textual)

Launch the modern Textual dashboard:

```bash
os-tui --interactive                  # Default: Textual mode
os-tui --interactive --mode textual   # Explicitly use Textual
os-tui --interactive --section config # Start with specific section
os-tui --interactive --interval 5.0   # Set 2s refresh interval
```

### Legacy BIOS Mode

The original BIOS-like interface is still available:

```bash
os-tui --interactive --mode bios  # Force BIOS mode
python -u src/main.py tui bios    # CLI: Direct BIOS invocation
```

### Dashboard Shortcut

New alias for Textual mode only:

```bash
python -u src/main.py tui dashboard
python -u src/main.py tui dashboard --interval 2.0 --section plugins
```

### JSON Snapshot Render

Render sections as JSON (works with or without Textual):

```bash
os-tui --section identity  # Print single section as JSON
python -u src/main.py tui render --section config
```

## Keyboard Shortcuts

### Navigation

| Key | Action |
|-----|--------|
| `1-6` | Jump to specific section (Identity, Config, Transport, Pipeline, Plugins, DB) |
| `Tab` / Arrow Keys | Navigate within current section |

### Controls

| Key | Action |
|-----|--------|
| `r` | Manually refresh current section |
| `a` | View all sections (overlay modal) |
| `i` | Set custom refresh interval |
| `j` | Show current section as JSON (modal) |
| `q` / `Ctrl+C` | Quit |

## Architecture

### File Structure

```
src/opensynaptic/services/tui/
├── __init__.py                    # Module exports
├── main.py                        # TUIService (data sources)
├── textual_app.py                 # Textual app & screens
├── styles.tcss                    # Textual CSS theme
└── widgets/
    ├── __init__.py
    ├── base_panel.py              # Abstract base widget
    ├── identity_panel.py          # Device ID, version, etc.
    ├── config_panel.py            # Configuration tree view
    ├── transport_panel.py         # Transporter status table
    ├── pipeline_panel.py          # Cache stats
    ├── plugins_panel.py           # Mounted plugins
    └── db_panel.py                # Database info
```

### Data Flow

1. **TUIService** (`main.py`) – maintains section renderers and data sources
2. **TextualTUIApp** (`textual_app.py`) – Textual App class with handlers
3. **Widgets** (`widgets/`) – individual section panels (currently using Static + JSON for simplicity)
4. **Screens** – Modal dialogs (JSON view, interval input)

### Design Pattern

- **Backward compatible** – all existing TUIService methods preserved
- **Graceful degradation** – falls back to BIOS if Textual import fails
- **Data-source agnostic** – widgets use TUIService.render_section() for data
- **Optional dependency** – Textual in `[project.optional-dependencies]`

## Rendering Modes

### Textual Mode (Interactive)

Full interactive dashboard with:
- Sidebar for section navigation
- Content area showing current section (JSON rendered in Static widget)
- Status bar with timestamp and refresh info
- Modal overlays for JSON view and interval input
- Keyboard bindings for all controls

### Fallback BIOS Mode

If Textual is not installed:
- ASCII-art bordered interface
- Numeric section selection (`1-6`)
- Interactive command loop with `input()` blocking

## Configuration

TUI service defaults (in `Config.json` or `plugin_registry.py`):

```json
"tui": {
  "enabled": true,
  "mode": "manual",
  "default_section": "identity",
  "default_interval": 2.0
}
```

## Development

### Adding a New Section

1. Create a new widget in `widgets/new_section_panel.py`:
   ```python
   from .base_panel import BaseTUIPanel
   
   class NewSectionPanel(BaseTUIPanel):
       def compose(self):
           # Return Textual widget(s)
       def render(self):
           # Text fallback
   ```

2. Add render method to `TUIService` in `main.py`:
   ```python
   def _section_newsection(self):
       return {...}
   
   # Add to _SECTION_METHODS dict
   ```

3. Register in `textual_app.py`:
   ```python
   from .widgets import NewSectionPanel
   _SECTION_PANELS["newsection"] = NewSectionPanel
   ```

### Testing

```bash
# Test Textual mode
python -u src/main.py tui interactive --interval 1.0

# Test BIOS fallback
python -u src/main.py tui interactive --mode bios

# Test JSON render
python -u src/main.py tui render --section identity

# Test without Textual (simulate missing dependency)
PYTHONNODEPS=1 python -u src/main.py tui interactive  # Will fallback
```

## Known Limitations & Future Improvements

- **Current widget implementation** uses Static + JSON text rendering for simplicity
  - Future: Replace with proper Textual widgets (DataTable, Tree) for better UX
  - Benefit: native sorting, filtering, scrolling in tables
  
- **Auto-refresh** currently on 1s timer; only updates if interval elapsed
  - Future: Use Textual's reactive binding or `set_timer` for precise intervals

- **Modal dialogs** are basic; no advanced validation
  - Future: Enhanced input validation and error feedback

- **Section views** are read-only
  - Future: Add editing capabilities for config/transporter settings

## Troubleshooting

### Textual falls back to BIOS automatically

**Cause:** Textual not installed or terminal incompatibility

**Solution:** Install Textual:
```bash
pip install textual>=0.40.0
```

### UI rendering issues

**Cause:** Terminal size too small or unsupported terminal type

**Solution:**
- Resize terminal to at least 80x24
- Try `--mode bios` for fallback
- Check terminal environment (Windows Terminal, iTerm2, etc. recommended)

### Commands not responding

**Cause:** Terminal input buffering

**Solution:**
- Ensure stdin is interactive (avoid piping input)
- Use keyboard shortcuts instead of named commands in Textual mode

## References

- **Textual Documentation**: https://textual.textualize.io/
- **OpenSynaptic TUI Docs**: `docs/` (to be added)
- **Plugin System**: `docs/PLUGIN_DEVELOPMENT_SPECIFICATION.md`

