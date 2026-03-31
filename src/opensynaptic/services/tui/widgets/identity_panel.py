"""Identity section panel widget."""

from typing import Any, Dict

try:
    from textual.widgets import Static, DataTable
    from textual.containers import Container, Vertical
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False

from .base_panel import BaseTUIPanel


class IdentityPanel(BaseTUIPanel):
    """Display device identity information (ID, version, etc.)."""

    DEFAULT_CSS = """
    IdentityPanel {
        height: 100%;
    }
    
    #identity-table {
        height: 100%;
    }
    """

    def compose(self):
        """Compose the panel widgets."""
        if not TEXTUAL_AVAILABLE:
            yield Static("Textual not available")
            return

        table = DataTable(id="identity-table")
        yield table

    def on_mount(self):
        """Set up the table on mount."""
        if not TEXTUAL_AVAILABLE:
            return

        self.get_data()
        self._update_table()

    def _update_table(self):
        """Update the DataTable with current data."""
        if not TEXTUAL_AVAILABLE:
            return

        table = self.query_one("#identity-table", DataTable)
        table.clear(columns=True)

        # Add columns
        table.add_column("Property", key="property")
        table.add_column("Value", key="value")

        # Add rows from data
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
        lines = ["=== Identity ==="]
        for key, value in self._data.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

