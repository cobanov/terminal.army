"""Arastirma queue mantigi.

Max 5 paralel research, seri zamanlama (build_service ile ayni pattern).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.game.constants import BuildingType, TechType
from backend.app.game.formulas import research_cost, research_time_seconds
from backend.app.game.tech_tree import check_research_prerequisites
from backend.app.models.building import Building
from backend.app.models.planet import Planet
from backend.app.models.queue import BuildQueue, QueueType
from backend.app.models.research import Research
from backend.app.models.universe import Universe
from backend.app.services.resource_service import refresh_planet_resources

MAX_RESEARCH_QUEUE = 5


async def get_user_tech_levels(db: AsyncSession, user_id: int) -> dict[TechType, int]:
    result = await db.execute(select(Research).where(Research.user_id == user_id))
    out: dict[TechType, int] = {}
    for r in result.scalars().all():
        try:
            out[TechType(r.tech_type)] = r.level
        except ValueError:
            continue
    return out


async def get_max_research_lab_level(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(Building.level)
        .join(Planet, Planet.id == Building.planet_id)
        .where(
            Planet.owner_user_id == user_id,
            Building.building_type == BuildingType.RESEARCH_LAB.value,
        )
    )
    levels = list(result.scalars().all())
    return max(levels) if levels else 0


async def _active_research_count(db: AsyncSession, user_id: int) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(BuildQueue)
        .where(
            BuildQueue.user_id == user_id,
            BuildQueue.queue_type == QueueType.RESEARCH.value,
            BuildQueue.cancelled.is_(False),
            BuildQueue.applied.is_(False),
        )
    )
    return int(result.scalar() or 0)


async def _pending_research(db: AsyncSession, user_id: int, tt: TechType) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(BuildQueue)
        .where(
            BuildQueue.user_id == user_id,
            BuildQueue.queue_type == QueueType.RESEARCH.value,
            BuildQueue.item_key == tt.value,
            BuildQueue.cancelled.is_(False),
            BuildQueue.applied.is_(False),
        )
    )
    return int(result.scalar() or 0)


async def _latest_research_finish(db: AsyncSession, user_id: int) -> datetime | None:
    result = await db.execute(
        select(BuildQueue.finished_at)
        .where(
            BuildQueue.user_id == user_id,
            BuildQueue.queue_type == QueueType.RESEARCH.value,
            BuildQueue.cancelled.is_(False),
            BuildQueue.applied.is_(False),
        )
        .order_by(BuildQueue.finished_at.desc())
        .limit(1)
    )
    val = result.scalar_one_or_none()
    if val is not None and val.tzinfo is None:
        val = val.replace(tzinfo=UTC)
    return val


async def queue_research(
    db: AsyncSession,
    user_id: int,
    planet_id: int,
    tech_type: TechType,
) -> BuildQueue:
    planet = await db.get(Planet, planet_id)
    if planet is None or planet.owner_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="planet not found")

    await refresh_planet_resources(db, planet_id)
    await db.refresh(planet)

    total = await _active_research_count(db, user_id)
    if total >= MAX_RESEARCH_QUEUE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"research queue full (max {MAX_RESEARCH_QUEUE})",
        )

    lab_result = await db.execute(
        select(Building.level).where(
            Building.planet_id == planet_id,
            Building.building_type == BuildingType.RESEARCH_LAB.value,
        )
    )
    lab_level = lab_result.scalar_one_or_none() or 0
    if lab_level < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="planet needs Research Lab level 1 or higher",
        )

    tech_levels = await get_user_tech_levels(db, user_id)
    max_lab = await get_max_research_lab_level(db, user_id)
    ok, missing = check_research_prerequisites(tech_type, max_lab, tech_levels)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"prereq not met: {', '.join(missing)}",
        )

    current_level = tech_levels.get(tech_type, 0)
    pending = await _pending_research(db, user_id, tech_type)
    target_level = current_level + pending + 1

    cm, cc, cd = research_cost(tech_type, target_level)
    if (
        planet.resources_metal < cm
        or planet.resources_crystal < cc
        or planet.resources_deuterium < cd
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="insufficient resources"
        )

    universe = await db.get(Universe, planet.universe_id)
    speed = float(universe.speed_research) if universe else 1.0
    seconds = research_time_seconds(cm, cc, lab_level, speed)

    planet.resources_metal = float(planet.resources_metal) - cm
    planet.resources_crystal = float(planet.resources_crystal) - cc
    planet.resources_deuterium = float(planet.resources_deuterium) - cd

    now = datetime.now(UTC)
    last_finish = await _latest_research_finish(db, user_id)
    start_at = max(now, last_finish) if last_finish else now
    finished_at = start_at + timedelta(seconds=seconds)

    queue = BuildQueue(
        planet_id=planet_id,
        user_id=user_id,
        queue_type=QueueType.RESEARCH.value,
        item_key=tech_type.value,
        target_level=target_level,
        cost_metal=cm,
        cost_crystal=cc,
        cost_deuterium=cd,
        started_at=start_at,
        finished_at=finished_at,
    )
    db.add(queue)
    await db.commit()
    await db.refresh(queue)
    return queue
