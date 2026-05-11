"""OGame TUI - tek-ekran slash-command REPL."""

from __future__ import annotations

from textual.app import App

from ogame_tui.client import OGameClient
from ogame_tui.screens.repl import ReplScreen


class OGameApp(App):
    TITLE = "Space Galactic"

    def __init__(self, base_url: str = "http://localhost:8000", token: str | None = None) -> None:
        super().__init__()
        self.client = OGameClient(base_url=base_url, token=token)
        self.current_planet_id: int | None = None
        self.current_universe_id: int | None = None
        self.planets: list[dict] = []
        self.me_info: dict | None = None

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
