"""Lazy resource update. Her API cagrisi planet'i refresh edebilir."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.game.constants import BuildingType, TechType
from backend.app.game.production import ProductionReport, compute_planet_production
from backend.app.models.building import Building
from backend.app.models.planet import Planet
from backend.app.models.research import Research
from backend.app.models.universe import Universe


async def get_user_researches(db: AsyncSession, user_id: int) -> dict[TechType, int]:
    result = await db.execute(select(Research).where(Research.user_id == user_id))
    out: dict[TechType, int] = {}
    for r in result.scalars().all():
        try:
            out[TechType(r.tech_type)] = r.level
        except ValueError:
            continue
    return out


async def get_planet_buildings(db: AsyncSession, planet_id: int) -> dict[BuildingType, int]:
    result = await db.execute(select(Building).where(Building.planet_id == planet_id))
    out: dict[BuildingType, int] = {}
    for b in result.scalars().all():
        try:
            out[BuildingType(b.building_type)] = b.level
        except ValueError:
            continue
    return out


async def compute_production_for_planet(db: AsyncSession, planet: Planet) -> ProductionReport:
    buildings = await get_planet_buildings(db, planet.id)
    researches = await get_user_researches(db, planet.owner_user_id)

    universe = await db.get(Universe, planet.universe_id)
    speed = float(universe.speed_economy) if universe else 1.0

    from backend.app.game.constants import (
        CRYSTAL_BONUS_BY_POSITION,
        METAL_BONUS_BY_POSITION,
    )

    return compute_planet_production(
        buildings=buildings,
        researches=researches,
        temp_min=planet.temp_min,
        temp_max=planet.temp_max,
        metal_position_bonus=METAL_BONUS_BY_POSITION.get(planet.position, 0.0),
        crystal_position_bonus=CRYSTAL_BONUS_BY_POSITION.get(planet.position, 0.0),
        speed=speed,
    )


async def refresh_planet_resources(
    db: AsyncSession,
    planet_id: int,
    now: datetime | None = None,
) -> tuple[Planet, ProductionReport]:
    now = now or datetime.now(UTC)
    # SELECT ... FOR UPDATE prevents two concurrent requests on the same
    # planet from both computing + applying the same delta_seconds. On
    # SQLite (solo mode) this is a no-op; on Postgres it serializes the
    # row update.
    result = await db.execute(select(Planet).where(Planet.id == planet_id).with_for_update())
    planet = result.scalar_one_or_none()
    if planet is None:
        raise ValueError(f"planet {planet_id} not found")

    last = planet.resources_last_updated_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    delta = (now - last).total_seconds()
    if delta < 0:
        delta = 0.0

    report = await compute_production_for_planet(db, planet)

    hours = delta / 3600.0
    planet.resources_metal = float(planet.resources_metal) + report.metal_per_hour * hours
    planet.resources_crystal = float(planet.resources_crystal) + report.crystal_per_hour * hours
    new_deut = float(planet.resources_deuterium) + report.deuterium_per_hour * hours
    planet.resources_deuterium = max(0.0, new_deut)
    planet.resources_last_updated_at = now

    await db.flush()
    return planet, report
