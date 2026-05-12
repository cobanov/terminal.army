"""Scheduler tarafindan kullanilan: tamamlanan queue itemlarini uygula."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.game.constants import BuildingType, DefenseType, ShipType, TechType
from backend.app.models.building import Building
from backend.app.models.planet import Planet
from backend.app.models.queue import BuildQueue, QueueType
from backend.app.models.research import Research
from backend.app.models.ship import PlanetDefense, PlanetShip


async def process_completed_queue(db: AsyncSession, now: datetime | None = None) -> int:
    """Tamamlanan queue itemlarini bul ve uygula. Uygulanan item sayisini doner."""
    now = now or datetime.now(UTC)
    result = await db.execute(
        select(BuildQueue).where(
            BuildQueue.cancelled.is_(False),
            BuildQueue.applied.is_(False),
            BuildQueue.finished_at <= now,
        )
    )
    items = result.scalars().all()
    applied_count = 0

    for item in items:
        if item.queue_type == QueueType.BUILDING.value:
            await _apply_building(db, item)
        elif item.queue_type == QueueType.RESEARCH.value:
            await _apply_research(db, item)
        elif item.queue_type == QueueType.SHIP.value:
            await _apply_ship(db, item)
        elif item.queue_type == QueueType.DEFENSE.value:
            await _apply_defense(db, item)
        else:
            continue
        item.applied = True
        applied_count += 1

    if applied_count > 0:
        await db.commit()
    return applied_count


async def _apply_building(db: AsyncSession, item: BuildQueue) -> None:
    try:
        bt = BuildingType(item.item_key)
    except ValueError:
        return
    result = await db.execute(
        select(Building).where(
            Building.planet_id == item.planet_id, Building.building_type == bt.value
        )
    )
    building = result.scalar_one_or_none()
    if building is None:
        building = Building(planet_id=item.planet_id, building_type=bt.value, level=0)
        db.add(building)
        await db.flush()
    # +1 (cancel-safe). target_level informational; queue ortasinda iptal olursa
    # kalanlar yine dogru tek-tek artar.
    building.level += 1

    planet = await db.get(Planet, item.planet_id)
    if planet is not None and planet.fields_used < planet.fields_total:
        planet.fields_used += 1


async def _apply_ship(db: AsyncSession, item: BuildQueue) -> None:
    """Add `target_level` (used as count) ships of `item_key` type to planet."""
    try:
        st = ShipType(item.item_key)
    except ValueError:
        return
    result = await db.execute(
        select(PlanetShip).where(
            PlanetShip.planet_id == item.planet_id, PlanetShip.ship_type == st.value
        )
    )
    ship_row = result.scalar_one_or_none()
    if ship_row is None:
        ship_row = PlanetShip(planet_id=item.planet_id, ship_type=st.value, count=0)
        db.add(ship_row)
        await db.flush()
    ship_row.count += item.target_level  # count field reused


async def _apply_defense(db: AsyncSession, item: BuildQueue) -> None:
    """Add `target_level` (used as count) defenses of `item_key` to planet."""
    try:
        dt = DefenseType(item.item_key)
    except ValueError:
        return
    result = await db.execute(
        select(PlanetDefense).where(
            PlanetDefense.planet_id == item.planet_id,
            PlanetDefense.defense_type == dt.value,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = PlanetDefense(planet_id=item.planet_id, defense_type=dt.value, count=0)
        db.add(row)
        await db.flush()
    row.count += item.target_level


async def _apply_research(db: AsyncSession, item: BuildQueue) -> None:
    try:
        tt = TechType(item.item_key)
    except ValueError:
        return
    result = await db.execute(
        select(Research).where(
            Research.user_id == item.user_id, Research.tech_type == tt.value
        )
    )
    research = result.scalar_one_or_none()
    if research is None:
        research = Research(user_id=item.user_id, tech_type=tt.value, level=0)
        db.add(research)
        await db.flush()
    research.level += 1
