from __future__ import annotations

from pydantic import BaseModel


class GalaxySlot(BaseModel):
    position: int
    planet_id: int | None
    planet_name: str | None
    owner_username: str | None


class GalaxyResponse(BaseModel):
    universe_id: int
    galaxy: int
    system: int
    slots: list[GalaxySlot]
