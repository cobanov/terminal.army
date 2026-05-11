from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import desc, select

from backend.app.deps import CurrentUser, DBSession
from backend.app.models.planet import Planet
from backend.app.models.queue import BuildQueue
from backend.app.schemas.planet import (
    EnergyStatus,
    PlanetDetailRead,
    PlanetRead,
    ProductionRates,
)
from backend.app.services.resource_service import refresh_planet_resources

router = APIRouter(prefix="/planets", tags=["planets"])


class PlanetLogEntry(BaseModel):
    id: int
    queue_type: str
    item_key: str
    target_level: int
    completed_at: datetime


@router.get("", response_model=list[PlanetRead])
async def list_planets(user: CurrentUser, db: DBSession) -> list[PlanetRead]:
    result = await db.execute(
        select(Planet).where(Planet.owner_user_id == user.id).order_by(Planet.id)
    )
    return [PlanetRead.model_validate(p) for p in result.scalars().all()]


@router.get("/{planet_id}/logs", response_model=list[PlanetLogEntry])
async def planet_logs(
    planet_id: int, user: CurrentUser, db: DBSession, limit: int = 20
) -> list[PlanetLogEntry]:
    """Recent completed queue items on this planet (newest first)."""
    planet = await db.get(Planet, planet_id)
    if planet is None or planet.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="planet not found")

    result = await db.execute(
        select(BuildQueue)
        .where(
            BuildQueue.planet_id == planet_id,
            BuildQueue.applied.is_(True),
        )
        .order_by(desc(BuildQueue.finished_at))
        .limit(limit)
    )
    items = result.scalars().all()
    return [
        PlanetLogEntry(
            id=q.id,
            queue_type=q.queue_type,
            item_key=q.item_key,
            target_level=q.target_level,
            completed_at=q.finished_at,
        )
        for q in items
    ]


@router.get("/{planet_id}", response_model=PlanetDetailRead)
async def get_planet(planet_id: int, user: CurrentUser, db: DBSession) -> PlanetDetailRead:
    planet = await db.get(Planet, planet_id)
    if planet is None or planet.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="planet not found")

    planet, report = await refresh_planet_resources(db, planet.id)
    await db.commit()
    await db.refresh(planet)

    base = PlanetRead.model_validate(planet)
    return PlanetDetailRead(
        **base.model_dump(),
        production=ProductionRates(
            metal_per_hour=report.metal_per_hour,
            crystal_per_hour=report.crystal_per_hour,
            deuterium_per_hour=report.deuterium_per_hour,
        ),
        energy=EnergyStatus(
            produced=report.energy_produced,
            consumed=report.energy_consumed,
            balance=report.energy_balance,
            production_factor=report.production_factor,
        ),
    )
