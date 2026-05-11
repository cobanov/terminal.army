"""Shipyard: batch ship construction.

Each call queues a BUILD_QUEUE item with queue_type="ship". Building time is
computed per ship (which uses Shipyard level + Nanite level multiplier).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.game.constants import (
    SHIP_PREREQUISITES,
    SHIP_STATS,
    BuildingType,
    ShipType,
    TechType,
)
from backend.app.game.formulas import build_time_seconds
from backend.app.models.building import Building
from backend.app.models.planet import Planet
from backend.app.models.queue import BuildQueue, QueueType
from backend.app.models.research import Research
from backend.app.models.universe import Universe
from backend.app.services.build_service import (
    _active_queue_count,
    _get_building_level,
    _latest_queue_finish,
)
from backend.app.services.resource_service import refresh_planet_resources

MAX_SHIPYARD_QUEUE = 5


async def _user_tech_levels(db: AsyncSession, user_id: int) -> dict[TechType, int]:
    res = await db.execute(select(Research).where(Research.user_id == user_id))
    out: dict[TechType, int] = {}
    for r in res.scalars().all():
        try:
            out[TechType(r.tech_type)] = r.level
        except ValueError:
            continue
    return out


async def _check_ship_prereq(
    db: AsyncSession, planet_id: int, user_id: int, ship_type: ShipType
) -> list[str]:
    reqs = SHIP_PREREQUISITES.get(ship_type, {})
    techs = await _user_tech_levels(db, user_id)
    missing: list[str] = []
    for k, v in reqs.items():
        if k == "shipyard":
            level = await _get_building_level(db, planet_id, BuildingType.SHIPYARD)
            if level < v:
                missing.append(f"Shipyard L{v} (have L{level})")
        else:
            try:
                tt = TechType(k)
            except ValueError:
                continue
            if techs.get(tt, 0) < v:
                missing.append(f"{tt.value} L{v}")
    return missing


async def queue_ship_build(
    db: AsyncSession,
    planet_id: int,
    user_id: int,
    ship_type: ShipType,
    count: int,
) -> BuildQueue:
    if count < 1 or count > 1000:
        raise HTTPException(status_code=400, detail="count must be 1..1000")

    planet = await db.get(Planet, planet_id)
    if planet is None or planet.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="planet not found")

    await refresh_planet_resources(db, planet_id)
    await db.refresh(planet)

    # Active SHIP-queue size
    total = await _active_queue_count(db, planet_id, QueueType.SHIP.value)
    if total >= MAX_SHIPYARD_QUEUE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"shipyard queue full (max {MAX_SHIPYARD_QUEUE})",
        )

    missing = await _check_ship_prereq(db, planet_id, user_id, ship_type)
    if missing:
        raise HTTPException(
            status_code=400, detail=f"prereq not met: {', '.join(missing)}"
        )

    m, c, d, *_ = SHIP_STATS[ship_type]
    tot_m, tot_c, tot_d = m * count, c * count, d * count
    if (
        planet.resources_metal < tot_m
        or planet.resources_crystal < tot_c
        or planet.resources_deuterium < tot_d
    ):
        raise HTTPException(
            status_code=400,
            detail=f"insufficient resources: need {tot_m}/{tot_c}/{tot_d}",
        )

    # Build time per ship (same formula as buildings) * count, with shipyard+nanite speedup
    shipyard_lvl = await _get_building_level(db, planet_id, BuildingType.SHIPYARD)
    nanite = await _get_building_level(db, planet_id, BuildingType.NANITE_FACTORY)
    universe = await db.get(Universe, planet.universe_id)
    speed = float(universe.speed_economy) if universe else 1.0
    per_ship_seconds = build_time_seconds(m, c, shipyard_lvl, nanite, speed)
    total_seconds = max(1, per_ship_seconds * count)

    # Spend resources
    planet.resources_metal = float(planet.resources_metal) - tot_m
    planet.resources_crystal = float(planet.resources_crystal) - tot_c
    planet.resources_deuterium = float(planet.resources_deuterium) - tot_d

    now = datetime.now(UTC)
    last_finish = await _latest_queue_finish(db, planet_id, QueueType.SHIP.value)
    start_at = max(now, last_finish) if last_finish else now
    finished_at = start_at + timedelta(seconds=total_seconds)

    queue = BuildQueue(
        planet_id=planet_id,
        user_id=user_id,
        queue_type=QueueType.SHIP.value,
        item_key=ship_type.value,
        target_level=count,  # using target_level field as count for SHIP queues
        cost_metal=tot_m,
        cost_crystal=tot_c,
        cost_deuterium=tot_d,
        started_at=start_at,
        finished_at=finished_at,
    )
    db.add(queue)
    await db.commit()
    await db.refresh(queue)
    return queue
