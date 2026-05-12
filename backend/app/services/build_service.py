"""Bina insaat queue mantigi.

Davranis:
- Bir gezegen icin max 5 paralel queue.
- Yeni item seri olarak sona eklenir: start_at = max(now, en gec queue finish).
- Ayni binayi 5 kez queue'ya atarsan target_level 1,2,3,4,5 olur (cost'lar buna gore).
- Cancel: yalnizca o item refund edilir; queue'da kalanlar +1 increment ile apply olur.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.game.constants import BuildingType
from backend.app.game.formulas import build_time_seconds, building_cost
from backend.app.models.building import Building
from backend.app.models.planet import Planet
from backend.app.models.queue import BuildQueue, QueueType
from backend.app.models.universe import Universe
from backend.app.services.resource_service import refresh_planet_resources

MAX_BUILDING_QUEUE = 5


async def _get_building_level(db: AsyncSession, planet_id: int, bt: BuildingType) -> int:
    result = await db.execute(
        select(Building).where(Building.planet_id == planet_id, Building.building_type == bt.value)
    )
    b = result.scalar_one_or_none()
    return b.level if b else 0


async def _active_queue_count(db: AsyncSession, planet_id: int, queue_type: str) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(BuildQueue)
        .where(
            BuildQueue.planet_id == planet_id,
            BuildQueue.queue_type == queue_type,
            BuildQueue.cancelled.is_(False),
            BuildQueue.applied.is_(False),
        )
    )
    return int(result.scalar() or 0)


async def _pending_upgrades_for_building(db: AsyncSession, planet_id: int, bt: BuildingType) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(BuildQueue)
        .where(
            BuildQueue.planet_id == planet_id,
            BuildQueue.queue_type == QueueType.BUILDING.value,
            BuildQueue.item_key == bt.value,
            BuildQueue.cancelled.is_(False),
            BuildQueue.applied.is_(False),
        )
    )
    return int(result.scalar() or 0)


async def _latest_queue_finish(
    db: AsyncSession, planet_id: int, queue_type: str
) -> datetime | None:
    result = await db.execute(
        select(BuildQueue.finished_at)
        .where(
            BuildQueue.planet_id == planet_id,
            BuildQueue.queue_type == queue_type,
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


async def queue_building_upgrade(
    db: AsyncSession,
    planet_id: int,
    user_id: int,
    building_type: BuildingType,
) -> BuildQueue:
    planet = await db.get(Planet, planet_id)
    if planet is None or planet.owner_user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="planet not found")

    await refresh_planet_resources(db, planet_id)
    await db.refresh(planet)

    total = await _active_queue_count(db, planet_id, QueueType.BUILDING.value)
    if total >= MAX_BUILDING_QUEUE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"queue full (max {MAX_BUILDING_QUEUE})",
        )

    current_level = await _get_building_level(db, planet_id, building_type)
    pending = await _pending_upgrades_for_building(db, planet_id, building_type)
    target_level = current_level + pending + 1

    cm, cc, cd = building_cost(building_type, target_level)
    if (
        planet.resources_metal < cm
        or planet.resources_crystal < cc
        or planet.resources_deuterium < cd
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"insufficient resources: need {cm}/{cc}/{cd}, "
                f"have {int(planet.resources_metal)}/{int(planet.resources_crystal)}/"
                f"{int(planet.resources_deuterium)}"
            ),
        )

    if planet.fields_used + pending >= planet.fields_total:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="no free fields on planet"
        )

    robotics = await _get_building_level(db, planet_id, BuildingType.ROBOTICS_FACTORY)
    nanite = await _get_building_level(db, planet_id, BuildingType.NANITE_FACTORY)
    universe = await db.get(Universe, planet.universe_id)
    speed = float(universe.speed_economy) if universe else 1.0

    seconds = build_time_seconds(cm, cc, robotics, nanite, speed)

    planet.resources_metal = float(planet.resources_metal) - cm
    planet.resources_crystal = float(planet.resources_crystal) - cc
    planet.resources_deuterium = float(planet.resources_deuterium) - cd

    now = datetime.now(UTC)
    last_finish = await _latest_queue_finish(db, planet_id, QueueType.BUILDING.value)
    start_at = max(now, last_finish) if last_finish else now
    finished_at = start_at + timedelta(seconds=seconds)

    queue = BuildQueue(
        planet_id=planet_id,
        user_id=user_id,
        queue_type=QueueType.BUILDING.value,
        item_key=building_type.value,
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


async def cancel_queue_item(db: AsyncSession, queue_id: int, user_id: int) -> BuildQueue:
    queue = await db.get(BuildQueue, queue_id)
    if queue is None or queue.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="queue item not found")
    if queue.cancelled or queue.applied:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="queue item already finalized"
        )

    # Lock the planet before refunding so a concurrent upgrade on the same
    # planet sees a consistent balance.
    locked = await db.execute(select(Planet).where(Planet.id == queue.planet_id).with_for_update())
    planet = locked.scalar_one_or_none()
    if planet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="planet not found")

    planet.resources_metal = float(planet.resources_metal) + queue.cost_metal
    planet.resources_crystal = float(planet.resources_crystal) + queue.cost_crystal
    planet.resources_deuterium = float(planet.resources_deuterium) + queue.cost_deuterium
    queue.cancelled = True
    await db.commit()
    await db.refresh(queue)
    return queue
