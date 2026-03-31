"""Transport section panel widget."""

from typing import Any, Dict

try:
    from textual.widgets import Static, DataTable
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False

from .base_panel import BaseTUIPanel


class TransportPanel(BaseTUIPanel):
    """Display transport/transporter status."""

    DEFAULT_CSS = """
    TransportPanel {
        height: 100%;
    }
    
    #transport-table {
        height: 100%;
    }
    """

    def compose(self):
        """Compose the panel widgets."""
        if not TEXTUAL_AVAILABLE:
            yield Static("Textual not available")
            return

        table = DataTable(id="transport-table")
        yield table

    def on_mount(self):
        """Set up the table on mount."""
        if not TEXTUAL_AVAILABLE:
            return

        self.get_data()
        self._update_table()

    def _update_table(self):
        """Update the DataTable with transport data."""
        if not TEXTUAL_AVAILABLE:
            return

        table = self.query_one("#transport-table", DataTable)
        table.clear(columns=True)

        data = self._data or {}

        # Show active transporters
        if "active_transporters" in data:
            table.add_column("Active Transporter", key="transporter")
            for transporter in data.get("active_transporters", []):
                table.add_row(transporter, key=transporter)
        else:
            # Show status maps
            table.add_column("Layer", key="layer")
            table.add_column("Status", key="status")

            for key in ["transporters_status", "transport_status", "physical_status", "application_status"]:
                if key in data:
                    status = data[key]
                    if isinstance(status, dict):
                        for k, v in status.items():
                            table.add_row(f"{key}/{k}", str(v), key=f"{key}/{k}")

    def refresh_data(self) -> None:
        """Refresh data and update table."""
        super().refresh_data()
        if TEXTUAL_AVAILABLE:
            self._update_table()

    def render(self) -> str:
        """Render as text (fallback for non-Textual mode)."""
        lines = ["=== Transport Status ==="]
        for key, value in self._data.items():
            if isinstance(value, list):
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
            elif isinstance(value, dict):
                lines.append(f"{key}:")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)

