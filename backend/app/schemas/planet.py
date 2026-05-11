from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PlanetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_user_id: int
    universe_id: int
    galaxy: int
    system: int
    position: int
    name: str
    fields_used: int
    fields_total: int
    temp_min: int
    temp_max: int
    resources_metal: float
    resources_crystal: float
    resources_deuterium: float
    resources_last_updated_at: datetime
    created_at: datetime


class ProductionRates(BaseModel):
    metal_per_hour: float
    crystal_per_hour: float
    deuterium_per_hour: float


class EnergyStatus(BaseModel):
    produced: int
    consumed: int
    balance: int
    production_factor: float


class PlanetDetailRead(PlanetRead):
    production: ProductionRates
    energy: EnergyStatus
