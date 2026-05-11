from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from backend.app.deps import DBSession
from backend.app.models.universe import Universe

router = APIRouter(prefix="/universes", tags=["universes"])


class UniverseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    speed_economy: int
    speed_fleet: int
    speed_research: int
    galaxies_count: int
    systems_count: int
    is_active: bool


@router.get("", response_model=list[UniverseRead])
async def list_universes(db: DBSession) -> list[UniverseRead]:
    result = await db.execute(select(Universe).order_by(Universe.id))
    return [UniverseRead.model_validate(u) for u in result.scalars().all()]
