from __future__ import annotations

from pydantic import BaseModel


class BuildingRead(BaseModel):
    building_type: str
    level: int
    next_cost_metal: int
    next_cost_crystal: int
    next_cost_deuterium: int
    next_build_seconds: int


class BuildingsResponse(BaseModel):
    planet_id: int
    buildings: list[BuildingRead]


class UpgradeResponse(BaseModel):
    queue_id: int
    item_key: str
    target_level: int
    finished_at: str
    cost_metal: int
    cost_crystal: int
    cost_deuterium: int
