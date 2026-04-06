"""Plugins section panel widget."""

from typing import Any, Dict

try:
    from textual.widgets import Static, DataTable
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False

from .base_panel import BaseTUIPanel


class PluginsPanel(BaseTUIPanel):
    """Display mounted plugins and their status."""

    DEFAULT_CSS = """
    PluginsPanel {
        height: 100%;
    }
    
    #plugins-table {
        height: 100%;
    }
    """

    def compose(self):
        """Compose the panel widgets."""
        if not TEXTUAL_AVAILABLE:
            yield Static("Textual not available")
            return

        table = DataTable(id="plugins-table")
        yield table

    def on_mount(self):
        """Set up the table on mount."""
        if not TEXTUAL_AVAILABLE:
            return

        try:
            self.get_data()
            self._update_table()
        except Exception as e:
            self.log.error(f"Failed to initialize plugins panel: {e}")

    def _update_table(self):
        """Update the DataTable with plugin data."""
        if not TEXTUAL_AVAILABLE:
            return

        try:
            table = self.query_one("#plugins-table", DataTable)
        except Exception:
            return
        table.clear(columns=True)

        data = self._data or {}

        if "mount_index" in data:
            # Show mounted plugins
            table.add_column("Mounted Plugin", key="plugin")
            for plugin in data.get("mount_index", []):
                table.add_row(plugin, key=plugin)

        if "runtime_index" in data:
            # Show runtime plugins
            runtime = data.get("runtime_index", {})
            if runtime:
                table.add_column("Runtime Plugin", key="runtime_plugin")
                for name, info in runtime.items():
                    status = "loaded" if info else "unloaded"
                    table.add_row(f"{name} ({status})", key=name)

    def refresh_data(self) -> None:
        """Refresh data and update table."""
        super().refresh_data()
        if TEXTUAL_AVAILABLE:
            self._update_table()

    def render(self) -> str:
        """Render as text (fallback for non-Textual mode)."""
        lines = ["=== Plugins ==="]
        data = self._data or {}

        if "mount_index" in data:
            lines.append("Mounted:")
            for plugin in data.get("mount_index", []):
                lines.append(f"  - {plugin}")

        if "runtime_index" in data:
            runtime = data.get("runtime_index", {})
            if runtime:
                lines.append("Runtime:")
                for name, info in runtime.items():
                    status = "loaded" if info else "unloaded"
                    lines.append(f"  - {name} ({status})")

        return "\n".join(lines)

