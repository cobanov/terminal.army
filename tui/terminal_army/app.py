"""terminal.army TUI - tek-ekran slash-command REPL."""

from __future__ import annotations

from textual.app import App
from textual.theme import Theme

from terminal_army import options
from terminal_army.client import TerminalArmyClient
from terminal_army.screens.repl import ReplScreen

# Our original look: deep black background, near-black panels, amber
# accents. Registered with Textual's theme system so /options --theme
# treats it like any other built-in.
TARMY_DARK = Theme(
    name="tarmy-dark",
    primary="#fbbf24",
    secondary="#84cc16",
    accent="#fbbf24",
    warning="#fbbf24",
    error="#ef4444",
    success="#84cc16",
    background="#000000",
    surface="#0a0a0a",
    panel="#0a0a0a",
    # `boost` is used as the panel-separator border color in our CSS.
    # Bumped from #262626 (barely visible against #0a0a0a panels) to a
    # mid-gray that actually reads as a divider.
    boost="#525252",
    foreground="#d4d4d4",
    dark=True,
)


class TerminalArmyApp(App):
    TITLE = "terminal.army"

    def __init__(self, base_url: str = "http://localhost:8000", token: str | None = None) -> None:
        super().__init__()
        self.client = TerminalArmyClient(base_url=base_url, token=token)
        self.current_planet_id: int | None = None
        self.current_universe_id: int | None = None
        self.planets: list[dict] = []
        self.me_info: dict | None = None
        # Register our default theme before applying any saved preference.
        # If the user has never run /options --theme this picks the
        # tarmy-dark palette; otherwise their saved name (built-in or
        # ours) is restored.
        try:
            self.register_theme(TARMY_DARK)
        except Exception:
            pass
        saved_theme = options.get_theme()
        try:
            self.theme = saved_theme
        except Exception:
            pass

    async def on_mount(self) -> None:
        # Bootstrap: kullanici ve planet info'sunu cek
        me = await self.client.me()
        self.me_info = me
        self.current_universe_id = me.get("current_universe_id")
        planets = await self.client.list_planets()
        self.planets = planets
        if planets:
            self.current_planet_id = planets[0]["id"]
        await self.push_screen(ReplScreen())

    async def on_unmount(self) -> None:
        await self.client.close()
