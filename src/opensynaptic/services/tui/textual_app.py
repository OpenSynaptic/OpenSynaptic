"""Textual-based TUI application for OpenSynaptic."""

import json
import time
from typing import Optional

from opensynaptic.utils import os_log, LogMsg

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
    from textual.widgets import Header, Footer, Static, Button, Input
    from textual.screen import Screen
    from textual.binding import Binding
    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    App = None
    ComposeResult = None
    Container = None
    Vertical = None
    Horizontal = None
    ScrollableContainer = None
    Header = None
    Footer = None
    Static = None
    Button = None
    Input = None
    Screen = None
    Binding = None


# Import panel widgets if Textual is available
if TEXTUAL_AVAILABLE:
    try:
        from .widgets import (
            IdentityPanel,
            ConfigPanel,
            TransportPanel,
            PipelinePanel,
            PluginsPanel,
            DBPanel,
        )
    except ImportError:
        IdentityPanel = None
        ConfigPanel = None
        TransportPanel = None
        PipelinePanel = None
        PluginsPanel = None
        DBPanel = None
else:
    IdentityPanel = None
    ConfigPanel = None
    TransportPanel = None
    PipelinePanel = None
    PluginsPanel = None
    DBPanel = None


_SECTION_PANELS = {
    "identity": IdentityPanel,
    "config": ConfigPanel,
    "transport": TransportPanel,
    "pipeline": PipelinePanel,
    "plugins": PluginsPanel,
    "db": DBPanel,
}


# Define screens only if Textual is available
if TEXTUAL_AVAILABLE:

    class JSONModalScreen(Screen):
        """Modal screen to display JSON data."""

        CSS = """
        JSONModalScreen {
            align: center middle;
        }

        #json-container {
            width: 80;
            height: 24;
            border: solid $primary;
            background: $surface;
        }

        #json-content {
            width: 100%;
            height: 100%;
        }
        """

        def __init__(self, json_data: str, **kwargs):
            super().__init__(**kwargs)
            self.json_data = json_data

        def compose(self) -> ComposeResult:
            """Compose the modal."""
            with Container(id="json-container"):
                yield Static(self.json_data, id="json-content")

        def on_mount(self):
            """Mount the modal."""
            try:
                content = self.query_one("#json-content", Static)
                content.border_title = "JSON View (ESC to close)"
            except Exception:
                pass

        def on_key(self, event):
            """Handle key press."""
            if hasattr(event, 'character') and event.character == "q":
                self.app.pop_screen()
            elif hasattr(event, 'key') and event.key == "escape":
                self.app.pop_screen()

    class IntervalInputScreen(Screen):
        """Modal screen to input refresh interval."""

        CSS = """
        IntervalInputScreen {
            align: center middle;
        }

        #input-container {
            width: 50;
            height: 8;
            border: solid $primary;
            background: $surface;
        }
        """

        def __init__(self, current_interval: float = 2.0, **kwargs):
            super().__init__(**kwargs)
            self.current_interval = current_interval
            self.new_interval = current_interval

        def compose(self) -> ComposeResult:
            """Compose the modal."""
            with Container(id="input-container"):
                yield Static(
                    f"Enter new refresh interval (current: {self.current_interval:.1f}s):\n"
                )
                yield Input(
                    value=str(self.current_interval),
                    id="interval-input",
                    type="number",
                )
                with Horizontal():
                    yield Button("OK", id="ok-btn", variant="primary")
                    yield Button("Cancel", id="cancel-btn")

        def on_mount(self):
            """Mount the modal."""
            try:
                self.query_one("#interval-input", Input).focus()
            except Exception:
                pass

        def on_button_pressed(self, event: Button.Pressed) -> None:
            """Handle button press."""
            if event.button.id == "ok-btn":
                try:
                    value = self.query_one("#interval-input", Input).value
                    self.new_interval = max(0.2, float(value))
                    self.app.post_message(self.SetInterval(self.new_interval))
                except (ValueError, AttributeError):
                    pass
                self.app.pop_screen()
            elif event.button.id == "cancel-btn":
                self.app.pop_screen()

        class SetInterval:
            """Message to set interval."""

            def __init__(self, interval: float):
                self.interval = interval

    class TextualDashboard(App):
        """Main Textual dashboard."""

        TITLE = "OpenSynaptic Dashboard"
        BINDINGS = [
            Binding("1", "section('identity')", "Identity"),
            Binding("2", "section('config')", "Config"),
            Binding("3", "section('transport')", "Transport"),
            Binding("4", "section('pipeline')", "Pipeline"),
            Binding("5", "section('plugins')", "Plugins"),
            Binding("6", "section('db')", "Database"),
            Binding("a", "all_sections", "All"),
            Binding("r", "refresh", "Refresh"),
            Binding("i", "set_interval", "Interval"),
            Binding("j", "show_json", "JSON"),
            Binding("q", "quit", "Quit"),
        ]

        DEFAULT_CSS = """
        Screen {
            layout: vertical;
        }

        Header {
            dock: top;
            height: 3;
            background: $boost;
            color: $text;
        }

        Footer {
            dock: bottom;
            height: 2;
            background: $boost;
            color: $text;
        }

        #main-container {
            height: 1fr;
            border: solid $primary;
        }

        #sidebar {
            width: 20;
            border-right: solid $primary;
            background: $panel;
            height: 1fr;
        }

        #content {
            height: 1fr;
            width: 1fr;
        }

        #status-bar {
            dock: bottom;
            height: 1;
            background: $boost;
            color: $text;
        }

        .section-button {
            margin: 0 1;
        }

        .section-button.active {
            background: $primary;
            color: $surface;
        }
        """

        def __init__(self, tui_service, initial_section: str, interval: float):
            super().__init__()
            self.tui_service = tui_service
            self.current_section = initial_section
            self.refresh_interval = interval
            self.last_refresh = time.time()
            self.current_panel = None

        def compose(self) -> ComposeResult:
            """Compose the app."""
            yield Header()

            with Horizontal(id="main-container"):
                with Vertical(id="sidebar"):
                    for section_name in _SECTION_PANELS.keys():
                        yield Button(
                            section_name,
                            id=f"btn-{section_name}",
                            classes="section-button",
                        )

                with ScrollableContainer(id="content"):
                    yield Static("Loading...", id="content-panel")

            yield Footer()
            yield Static("Ready", id="status-bar")

        def on_mount(self):
            """Mount the app."""
            os_log.log_with_const(
                "info", LogMsg.TUI_INTERACTIVE, interval=self.refresh_interval
            )
            self._refresh_content()
            self.set_interval(1.0, self._auto_refresh)

        def _update_status(self, msg: str):
            """Update status bar."""
            try:
                status = self.query_one("#status-bar", Static)
                now = time.strftime("%H:%M:%S")
                status.update(
                    f"[{now}] Section: {self.current_section} | Interval: {self.refresh_interval:.1f}s | {msg}"
                )
            except Exception:
                pass

        def _refresh_content(self):
            """Refresh the content panel."""
            try:
                content_widget = self.query_one("#content-panel", Static)
                data = self.tui_service.render_section(self.current_section)
                content_text = json.dumps(
                    data, indent=2, ensure_ascii=False, default=str
                )
                content_widget.update(content_text)
                self.last_refresh = time.time()
                self._update_status("Ready")
            except Exception as e:
                self._update_status(f"Error: {e}")

        def _auto_refresh(self):
            """Auto-refresh on interval."""
            if (
                time.time() - self.last_refresh >= self.refresh_interval
            ):
                self._refresh_content()

        def action_section(self, section: str):
            """Switch to a section."""
            if section in _SECTION_PANELS:
                self.current_section = section
                self._refresh_content()

        def action_refresh(self):
            """Manually refresh."""
            self._refresh_content()

        def action_all_sections(self):
            """Show all sections."""
            try:
                data = self.tui_service.render_sections()
                json_text = json.dumps(
                    data, indent=2, ensure_ascii=False, default=str
                )
                self.push_screen(JSONModalScreen(json_text))
            except Exception as e:
                self._update_status(f"Error: {e}")

        def action_show_json(self):
            """Show current section as JSON."""
            try:
                data = self.tui_service.render_section(self.current_section)
                json_text = json.dumps(
                    data, indent=2, ensure_ascii=False, default=str
                )
                self.push_screen(JSONModalScreen(json_text))
            except Exception as e:
                self._update_status(f"Error: {e}")

        def action_set_interval(self):
            """Set refresh interval."""
            self.push_screen(
                IntervalInputScreen(self.refresh_interval)
            )


class TextualTUIApp:
    """Textual-based TUI application wrapper that gracefully handles missing Textual."""

    def __init__(self, tui_service, interval: float = 2.0, section: Optional[str] = None):
        """Initialize the Textual TUI app.

        Args:
            tui_service: Reference to TUIService instance
            interval: Refresh interval in seconds
            section: Initial section to display
        """
        self.tui_service = tui_service
        self.interval = max(0.2, interval)
        self.section = (section or "identity").lower()
        self.textual_app = None

        if not TEXTUAL_AVAILABLE:
            os_log.info(
                "TUI",
                "NO_TEXTUAL",
                "Textual not installed; falling back to BIOS mode",
                {},
            )
            raise ImportError("Textual not available; use bios mode as fallback")

    def run(self):
        """Run the Textual app."""
        if not TEXTUAL_AVAILABLE:
            raise ImportError("Textual is not available")
        
        try:
            app = TextualDashboard(
                self.tui_service, self.section, self.interval
            )
            app.run()
        except Exception as e:
            os_log.err(
                "TUI",
                "RUN_ERROR",
                e,
                {"message": "Error running Textual TUI"},
            )
            raise

    def run_once(self):
        """Run the app once (snapshot mode)."""
        try:
            # Single-frame render for testing
            data = self.tui_service.render_section(self.section)
            return json.dumps(
                data, indent=2, ensure_ascii=False, default=str
            )
        except Exception as e:
            os_log.err(
                "TUI",
                "RENDER_ERROR",
                e,
                {"message": "Error rendering TUI"},
            )
            raise


