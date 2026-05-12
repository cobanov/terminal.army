"""Defense: batch construction of planetary defenses.

Each call queues a BUILD_QUEUE item with queue_type="defense". Build time
uses the same shipyard formula as ships, since defenses share the shipyard
production line on OGame.

Source: https://ogame.fandom.com/wiki/Defense
    Time(hours) = (Metal + Crystal) / (2500 * (1 + Shipyard) * 2^Nanite)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.game.constants import (
    DEFENSE_PREREQUISITES,
    DEFENSE_STATS,
    BuildingType,
    DefenseType,
    TechType,
)
from backend.app.game.formulas import build_time_seconds
from backend.app.models.planet import Planet
from backend.app.models.queue import BuildQueue, QueueType
from backend.app.models.research import Research
from backend.app.models.ship import PlanetDefense
from backend.app.models.universe import Universe
from backend.app.services.build_service import (
    _active_queue_count,
    _get_building_level,
    _latest_queue_finish,
)
from backend.app.services.resource_service import refresh_planet_resources

MAX_DEFENSE_QUEUE = 5
# Unlike turrets, shield domes are unique-per-planet (max 1).
UNIQUE_DEFENSES: frozenset[DefenseType] = frozenset({
    DefenseType.SMALL_SHIELD_DOME,
    DefenseType.LARGE_SHIELD_DOME,
})


async def _user_tech_levels(db: AsyncSession, user_id: int) -> dict[TechType, int]:
    res = await db.execute(select(Research).where(Research.user_id == user_id))
    out: dict[TechType, int] = {}
    for r in res.scalars().all():
        try:
            out[TechType(r.tech_type)] = r.level
        except ValueError:
            continue
    return out


async def _check_defense_prereq(
    db: AsyncSession, planet_id: int, user_id: int, dt: DefenseType
) -> list[str]:
    reqs = DEFENSE_PREREQUISITES.get(dt, {})
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


async def _current_count(
    db: AsyncSession, planet_id: int, dt: DefenseType
) -> int:
    """Built + queued (not yet applied) count of a given defense type."""
    built_res = await db.execute(
        select(PlanetDefense).where(
            PlanetDefense.planet_id == planet_id,
            PlanetDefense.defense_type == dt.value,
        )
    )
    row = built_res.scalar_one_or_none()
    built = row.count if row else 0
    queued_res = await db.execute(
        select(BuildQueue).where(
            BuildQueue.planet_id == planet_id,
            BuildQueue.queue_type == QueueType.DEFENSE.value,
            BuildQueue.item_key == dt.value,
            BuildQueue.cancelled.is_(False),
            BuildQueue.applied.is_(False),
        )
    )
    queued = sum(q.target_level for q in queued_res.scalars().all())
    return built + queued


async def queue_defense_build(
    db: AsyncSession,
    planet_id: int,
    user_id: int,
    defense_type: DefenseType,
    count: int,
) -> BuildQueue:
    if count < 1 or count > 1000:
        raise HTTPException(status_code=400, detail="count must be 1..1000")

    planet = await db.get(Planet, planet_id)
    if planet is None or planet.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="planet not found")

    await refresh_planet_resources(db, planet_id)
    await db.refresh(planet)

    total = await _active_queue_count(db, planet_id, QueueType.DEFENSE.value)
    if total >= MAX_DEFENSE_QUEUE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"defense queue full (max {MAX_DEFENSE_QUEUE})",
        )

    if defense_type in UNIQUE_DEFENSES:
        existing = await _current_count(db, planet_id, defense_type)
        if existing + count > 1:
            raise HTTPException(
                status_code=400,
                detail=f"{defense_type.value} is unique per planet (max 1)",
            )

    missing = await _check_defense_prereq(db, planet_id, user_id, defense_type)
    if missing:
        raise HTTPException(
            status_code=400, detail=f"prereq not met: {', '.join(missing)}"
        )

    m, c, d, *_ = DEFENSE_STATS[defense_type]
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

    shipyard_lvl = await _get_building_level(db, planet_id, BuildingType.SHIPYARD)
    nanite = await _get_building_level(db, planet_id, BuildingType.NANITE_FACTORY)
    universe = await db.get(Universe, planet.universe_id)
    speed = float(universe.speed_economy) if universe else 1.0
    per_unit_seconds = build_time_seconds(m, c, shipyard_lvl, nanite, speed)
    total_seconds = max(1, per_unit_seconds * count)

    planet.resources_metal = float(planet.resources_metal) - tot_m
    planet.resources_crystal = float(planet.resources_crystal) - tot_c
    planet.resources_deuterium = float(planet.resources_deuterium) - tot_d

    now = datetime.now(UTC)
    last_finish = await _latest_queue_finish(db, planet_id, QueueType.DEFENSE.value)
    start_at = max(now, last_finish) if last_finish else now
    finished_at = start_at + timedelta(seconds=total_seconds)

    queue = BuildQueue(
        planet_id=planet_id,
        user_id=user_id,
        queue_type=QueueType.DEFENSE.value,
        item_key=defense_type.value,
        target_level=count,
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
