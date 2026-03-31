"""Base panel class for TUI widgets."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

try:
    from textual.widget import Widget
    from textual.containers import Container
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    Widget = object
    Container = object


class BaseTUIPanel(Widget if TEXTUAL_AVAILABLE else ABC):
    """Abstract base class for TUI section panels."""

    DEFAULT_CSS = """
    BaseTUIPanel {
        border: solid $primary;
        height: 100%;
    }
    """

    def __init__(self, name: str, tui_service, *args, **kwargs):
        """Initialize the panel.
        
        Args:
            name: Section name (e.g., 'identity', 'config')
            tui_service: Reference to the TUIService instance
        """
        super().__init__(*args, **kwargs)
        self.name = name
        self.tui_service = tui_service
        self._data: Dict[str, Any] = {}

    def get_data(self) -> Dict[str, Any]:
        """Fetch data from TUIService for this section."""
        if hasattr(self.tui_service, 'render_section'):
            self._data = self.tui_service.render_section(self.name)
        return self._data

    @abstractmethod
    def render(self) -> str:
        """Render the panel content. Must be implemented by subclasses.
        
        Returns:
            Rendered content string or Textual widget
        """
        pass

    def refresh_data(self) -> None:
        """Refresh data and re-render."""
        self.get_data()
        if TEXTUAL_AVAILABLE:
            self.refresh()

