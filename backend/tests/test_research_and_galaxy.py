from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.app.db import AsyncSessionLocal
from backend.app.models.building import Building
from backend.app.models.queue import BuildQueue
from backend.app.scheduler import run_tick_once


async def _register(client, name: str) -> tuple[str, int]:
    await client.post(
        "/auth/register",
        json={"username": name, "email": f"{name}@example.com", "password": "secret1pass"},
    )
    r = await client.post("/auth/login", data={"username": name, "password": "secret1pass"})
    token = r.json()["access_token"]
    r = await client.get("/planets", headers={"Authorization": f"Bearer {token}"})
    return token, r.json()[0]["id"]


async def test_research_requires_research_lab(client) -> None:
    token, planet_id = await _register(client, "res1")
    r = await client.post(
        f"/researches/energy/upgrade?planet_id={planet_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400  # no research lab


async def test_research_flow_with_lab(client) -> None:
    token, planet_id = await _register(client, "res2")

    # Manually set lab level 1 and give resources
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Building).where(
                Building.planet_id == planet_id,
                Building.building_type == "research_lab",
            )
        )
        lab = result.scalar_one()
        lab.level = 1

        from backend.app.models.planet import Planet

        planet = await db.get(Planet, planet_id)
        planet.resources_metal = 10000
        planet.resources_crystal = 10000
        planet.resources_deuterium = 10000
        await db.commit()

    r = await client.post(
        f"/researches/energy/upgrade?planet_id={planet_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    queue_id = r.json()["queue_id"]

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BuildQueue).where(BuildQueue.id == queue_id))
        q = result.scalar_one()
        q.finished_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()
    await run_tick_once()

    r = await client.get("/researches", headers={"Authorization": f"Bearer {token}"})
    researches = {row["tech_type"]: row["level"] for row in r.json()["researches"]}
    assert researches["energy"] == 1


async def test_galaxy_view(client) -> None:
    token, planet_id = await _register(client, "gal1")
    r = await client.get(f"/planets/{planet_id}", headers={"Authorization": f"Bearer {token}"})
    p = r.json()

    r = await client.get(
        f"/galaxy?universe_id={p['universe_id']}&galaxy={p['galaxy']}&system={p['system']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["slots"]) == 15
    occupied = [s for s in body["slots"] if s["planet_id"] is not None]
    assert any(s["planet_id"] == planet_id for s in occupied)
    # Owner username present
    assert occupied[0]["owner_username"] == "gal1"
