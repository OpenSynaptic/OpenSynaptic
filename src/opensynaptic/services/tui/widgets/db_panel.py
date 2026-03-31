"""Database section panel widget."""

from typing import Any, Dict

try:
    from textual.widgets import Static, DataTable
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False

from .base_panel import BaseTUIPanel


class DBPanel(BaseTUIPanel):
    """Display database driver and status."""

    DEFAULT_CSS = """
    DBPanel {
        height: 100%;
    }
    
    #db-table {
        height: 100%;
    }
    """

    def compose(self):
        """Compose the panel widgets."""
        if not TEXTUAL_AVAILABLE:
            yield Static("Textual not available")
            return

        table = DataTable(id="db-table")
        yield table

    def on_mount(self):
        """Set up the table on mount."""
        if not TEXTUAL_AVAILABLE:
            return

        self.get_data()
        self._update_table()

    def _update_table(self):
        """Update the DataTable with DB data."""
        if not TEXTUAL_AVAILABLE:
            return

        table = self.query_one("#db-table", DataTable)
        table.clear(columns=True)

        table.add_column("Property", key="property")
        table.add_column("Value", key="value")

        data = self._data or {}
        for key, value in data.items():
            table.add_row(key, str(value), key=key)

    def refresh_data(self) -> None:
        """Refresh data and update table."""
        super().refresh_data()
        if TEXTUAL_AVAILABLE:
            self._update_table()

    def render(self) -> str:
        """Render as text (fallback for non-Textual mode)."""
        lines = ["=== Database ==="]
        for key, value in self._data.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

