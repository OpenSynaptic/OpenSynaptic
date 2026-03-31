"""Config section panel widget."""

import json
from typing import Any, Dict

try:
    from textual.widgets import Static, Tree
    from textual.text import Text
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False

from .base_panel import BaseTUIPanel


class ConfigPanel(BaseTUIPanel):
    """Display configuration settings in expandable tree view."""

    DEFAULT_CSS = """
    ConfigPanel {
        height: 100%;
    }
    
    #config-tree {
        height: 100%;
    }
    """

    def compose(self):
        """Compose the panel widgets."""
        if not TEXTUAL_AVAILABLE:
            yield Static("Textual not available")
            return

        tree = Tree(label="Config", id="config-tree")
        yield tree

    def on_mount(self):
        """Set up the tree on mount."""
        if not TEXTUAL_AVAILABLE:
            return

        self.get_data()
        self._update_tree()

    def _update_tree(self):
        """Update the Tree with current config data."""
        if not TEXTUAL_AVAILABLE:
            return

        tree = self.query_one("#config-tree", Tree)
        tree.clear()

        data = self._data or {}
        self._add_tree_nodes(tree.root, data)

    def _add_tree_nodes(self, parent, data: Dict[str, Any], depth: int = 0) -> None:
        """Recursively add nodes to tree."""
        if not isinstance(data, dict):
            return

        for key, value in data.items():
            if isinstance(value, dict):
                node = parent.add(key)
                self._add_tree_nodes(node, value, depth + 1)
            else:
                parent.add(f"{key}: {value}")

    def refresh_data(self) -> None:
        """Refresh data and update tree."""
        super().refresh_data()
        if TEXTUAL_AVAILABLE:
            self._update_tree()

    def render(self) -> str:
        """Render as text (fallback for non-Textual mode)."""
        return json.dumps(self._data, indent=2, ensure_ascii=False, default=str)

