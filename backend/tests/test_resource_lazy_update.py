from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.app.db import AsyncSessionLocal
from backend.app.models.building import Building
from backend.app.models.planet import Planet
from backend.app.services.resource_service import refresh_planet_resources


async def _register(client, name: str) -> str:
    await client.post(
        "/auth/register",
        json={"username": name, "email": f"{name}@example.com", "password": "secret1pass"},
    )
    r = await client.post("/auth/login", data={"username": name, "password": "secret1pass"})
    return r.json()["access_token"]


async def test_lazy_update_passive_metal(client) -> None:
    token = await _register(client, "lazy1")
    r = await client.get("/planets", headers={"Authorization": f"Bearer {token}"})
    planet_id = r.json()[0]["id"]

    # Time-travel: 1 hour
    async with AsyncSessionLocal() as db:
        planet = await db.get(Planet, planet_id)
        planet.resources_last_updated_at = datetime.now(UTC) - timedelta(hours=1)
        await db.commit()

    r = await client.get(f"/planets/{planet_id}", headers={"Authorization": f"Bearer {token}"})
    body = r.json()
    # Level 0 madenler base passive 30 m/h + 15 c/h verir
    assert body["resources_metal"] >= 500 + 29
    assert body["resources_crystal"] >= 500 + 14


async def test_lazy_update_with_metal_mine_level(client) -> None:
    """Level 10 mine but no solar plant => energy_consumed>0, production_factor=0,
    so mine output is throttled to zero and only base passive remains."""
    token = await _register(client, "lazy2")
    r = await client.get("/planets", headers={"Authorization": f"Bearer {token}"})
    planet_id = r.json()[0]["id"]

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Building).where(
                Building.planet_id == planet_id,
                Building.building_type == "metal_mine",
            )
        )
        mine = result.scalar_one()
        mine.level = 10
        await db.commit()

    async with AsyncSessionLocal() as db:
        _, report = await refresh_planet_resources(
            db, planet_id, now=datetime.now(UTC) + timedelta(hours=1)
        )
        await db.commit()
        assert report.energy_consumed > 0
        assert report.production_factor == 0.0
        # Base passive still produces 30/h
        assert report.metal_per_hour == 30.0


async def test_lazy_update_mine_with_solar_plant(client) -> None:
    """Level 5 metal mine + level 10 solar plant => energy positive,
    mine actually produces."""
    token = await _register(client, "lazy3")
    r = await client.get("/planets", headers={"Authorization": f"Bearer {token}"})
    planet_id = r.json()[0]["id"]

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Building).where(Building.planet_id == planet_id))
        for b in result.scalars().all():
            if b.building_type == "metal_mine":
                b.level = 5
            elif b.building_type == "solar_plant":
                b.level = 10
        await db.commit()

    async with AsyncSessionLocal() as db:
        _, report = await refresh_planet_resources(
            db, planet_id, now=datetime.now(UTC) + timedelta(hours=1)
        )
        assert report.production_factor == 1.0
        assert report.metal_per_hour > 30.0
