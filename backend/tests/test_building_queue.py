from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.app.db import AsyncSessionLocal
from backend.app.models.planet import Planet
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


async def test_upgrade_metal_mine_deducts_resources(client) -> None:
    token, planet_id = await _register(client, "build1")
    r = await client.post(
        f"/planets/{planet_id}/buildings/metal_mine/upgrade",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["target_level"] == 1

    async with AsyncSessionLocal() as db:
        planet = await db.get(Planet, planet_id)
        # Metal mine level 1 cost = 60 metal, 15 crystal. Started with 500/500.
        # Lazy update may add tiny passive amount, so allow some tolerance.
        assert 500 - 60 <= planet.resources_metal < 500
        assert 500 - 15 <= planet.resources_crystal < 500

    # Aynı bina ikinci kez queue'lanir: target_level = 2
    r = await client.post(
        f"/planets/{planet_id}/buildings/metal_mine/upgrade",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["target_level"] == 2


async def test_max_5_queue_then_409(client) -> None:
    """Bir gezegende max 5 paralel building queue, 6.cisinda 409 doner."""
    token, planet_id = await _register(client, "build_max")
    # Kaynak hazirla
    async with AsyncSessionLocal() as db:
        from backend.app.models.planet import Planet

        p = await db.get(Planet, planet_id)
        p.resources_metal = 100_000
        p.resources_crystal = 100_000
        p.resources_deuterium = 100_000
        await db.commit()

    for i in range(5):
        r = await client.post(
            f"/planets/{planet_id}/buildings/metal_mine/upgrade",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201, f"queue #{i + 1} failed: {r.text}"
        assert r.json()["target_level"] == i + 1

    # 6.ci 409
    r = await client.post(
        f"/planets/{planet_id}/buildings/metal_mine/upgrade",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409


async def test_queue_serial_scheduling(client) -> None:
    """Queue'daki itemler seri (start_at = onceki finished_at)."""
    from datetime import datetime

    token, planet_id = await _register(client, "build_serial")
    async with AsyncSessionLocal() as db:
        from backend.app.models.planet import Planet

        p = await db.get(Planet, planet_id)
        p.resources_metal = 100_000
        p.resources_crystal = 100_000
        await db.commit()

    finished_times = []
    for _ in range(3):
        r = await client.post(
            f"/planets/{planet_id}/buildings/metal_mine/upgrade",
            headers={"Authorization": f"Bearer {token}"},
        )
        finished_times.append(r.json()["finished_at"])

    # Her finished_at oncekinden buyuk
    dts = [datetime.fromisoformat(t) for t in finished_times]
    assert dts[0] < dts[1] < dts[2], f"not serial: {dts}"


async def test_upgrade_insufficient_resources_returns_400(client) -> None:
    token, planet_id = await _register(client, "build2")
    # Try to build a very expensive building right away
    r = await client.post(
        f"/planets/{planet_id}/buildings/fusion_reactor/upgrade",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


async def test_scheduler_applies_completed_queue(client) -> None:
    token, planet_id = await _register(client, "build3")
    r = await client.post(
        f"/planets/{planet_id}/buildings/metal_mine/upgrade",
        headers={"Authorization": f"Bearer {token}"},
    )
    queue_id = r.json()["queue_id"]

    # Force finished_at to past
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(BuildQueue).where(BuildQueue.id == queue_id))
        q = result.scalar_one()
        q.finished_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

    applied = await run_tick_once()
    assert applied >= 1

    r = await client.get(
        f"/planets/{planet_id}/buildings",
        headers={"Authorization": f"Bearer {token}"},
    )
    levels = {b["building_type"]: b["level"] for b in r.json()["buildings"]}
    assert levels["metal_mine"] == 1


async def test_cancel_queue_refunds(client) -> None:
    token, planet_id = await _register(client, "build4")
    r = await client.post(
        f"/planets/{planet_id}/buildings/metal_mine/upgrade",
        headers={"Authorization": f"Bearer {token}"},
    )
    queue_id = r.json()["queue_id"]
    cost_metal = r.json()["cost_metal"]
    cost_crystal = r.json()["cost_crystal"]

    r = await client.delete(f"/queue/{queue_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200

    async with AsyncSessionLocal() as db:
        planet = await db.get(Planet, planet_id)
        # OGame-style: cancel refunds 50% of the cost. Starting at 500/500,
        # we spent cost_metal/cost_crystal and get back half. Passive
        # production has added a tiny bit.
        expected_metal = 500 - cost_metal + cost_metal // 2
        expected_crystal = 500 - cost_crystal + cost_crystal // 2
        assert planet.resources_metal >= expected_metal
        assert planet.resources_metal < 500  # confirm not full refund
        assert planet.resources_crystal >= expected_crystal
