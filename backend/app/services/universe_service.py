from __future__ import annotations

import random
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.game.colonization import generate_planet_attributes
from backend.app.game.constants import (
    STARTING_CRYSTAL,
    STARTING_DEUTERIUM,
    STARTING_METAL,
    BuildingType,
    TechType,
)
from backend.app.models.building import Building
from backend.app.models.planet import Planet
from backend.app.models.research import Research
from backend.app.models.universe import Universe


async def get_default_universe(db: AsyncSession) -> Universe | None:
    result = await db.execute(
        select(Universe).where(Universe.is_active.is_(True)).order_by(Universe.id).limit(1)
    )
    return result.scalar_one_or_none()


async def ensure_default_universe(
    db: AsyncSession,
    name: str = "Galactica",
    speed: int = 1,
) -> Universe:
    existing = await get_default_universe(db)
    if existing is not None:
        return existing
    universe = Universe(
        name=name,
        speed_economy=speed,
        speed_fleet=speed,
        speed_research=speed,
        galaxies_count=9,
        systems_count=499,
        is_active=True,
    )
    db.add(universe)
    await db.commit()
    await db.refresh(universe)
    return universe


async def assign_starting_planet(
    db: AsyncSession,
    user_id: int,
    universe: Universe,
    rng: random.Random | None = None,
    max_tries: int = 50,
) -> Planet:
    """Random bos slota planet yarat. Race-safe (UNIQUE retry)."""
    rng = rng or random.Random()
    for _ in range(max_tries):
        galaxy = rng.randint(1, universe.galaxies_count)
        system = rng.randint(1, universe.systems_count)
        position = rng.randint(4, 12)
        attrs = generate_planet_attributes(position, rng)

        planet = Planet(
            owner_user_id=user_id,
            universe_id=universe.id,
            galaxy=galaxy,
            system=system,
            position=position,
            name="Homeworld",
            fields_used=0,
            fields_total=attrs.fields_total,
            temp_min=attrs.temp_min,
            temp_max=attrs.temp_max,
            resources_metal=float(STARTING_METAL),
            resources_crystal=float(STARTING_CRYSTAL),
            resources_deuterium=float(STARTING_DEUTERIUM),
            resources_last_updated_at=datetime.now(UTC),
        )
        db.add(planet)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            continue

        # Bootstrap building rows (level 0 each)
        for bt in BuildingType:
            db.add(Building(planet_id=planet.id, building_type=bt.value, level=0))
        await db.flush()
        await db.commit()
        await db.refresh(planet)
        return planet

    raise RuntimeError("no free slot found after many tries")


async def ensure_user_researches(db: AsyncSession, user_id: int) -> None:
    """Tum tech_type'lari level 0 olarak insert et (idempotent)."""
    result = await db.execute(select(Research).where(Research.user_id == user_id))
    existing = {r.tech_type for r in result.scalars().all()}
    for tt in TechType:
        if tt.value not in existing:
            db.add(Research(user_id=user_id, tech_type=tt.value, level=0))
    await db.flush()


async def backfill_planet_buildings(db: AsyncSession) -> int:
    """Mevcut tum planet'lar icin eksik BuildingType rows insert et.

    Yeni bina turleri (Missile Silo, Alliance Depot, vs.) eklendiginde,
    eski planet'larin da bu binalara level=0 satirina sahip olmasini saglar.
    """
    from backend.app.models.planet import Planet

    result = await db.execute(select(Planet.id))
    planet_ids = list(result.scalars().all())
    added = 0
    for pid in planet_ids:
        exist_result = await db.execute(
            select(Building.building_type).where(Building.planet_id == pid)
        )
        existing = set(exist_result.scalars().all())
        for bt in BuildingType:
            if bt.value not in existing:
                db.add(Building(planet_id=pid, building_type=bt.value, level=0))
                added += 1
    if added:
        await db.commit()
    return added


async def backfill_user_researches(db: AsyncSession) -> int:
    """Existing kullanicilar icin eksik TechType rows insert et (Combustion Drive, etc.)."""
    from backend.app.models.user import User

    res = await db.execute(select(User.id))
    user_ids = list(res.scalars().all())
    added = 0
    for uid in user_ids:
        existing_res = await db.execute(
            select(Research.tech_type).where(Research.user_id == uid)
        )
        existing = set(existing_res.scalars().all())
        for tt in TechType:
            if tt.value not in existing:
                db.add(Research(user_id=uid, tech_type=tt.value, level=0))
                added += 1
    if added:
        await db.commit()
    return added
