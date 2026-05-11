from __future__ import annotations


async def test_register_login_me_flow(client) -> None:
    r = await client.post(
        "/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": "secret1"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["username"] == "alice"
    assert body["current_universe_id"] is not None

    r = await client.post(
        "/auth/login",
        data={"username": "alice", "password": "secret1"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]

    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


async def test_register_duplicate_username(client) -> None:
    await client.post(
        "/auth/register",
        json={"username": "bob", "email": "bob@example.com", "password": "secret1"},
    )
    r = await client.post(
        "/auth/register",
        json={"username": "bob", "email": "bob2@example.com", "password": "secret1"},
    )
    assert r.status_code == 409


async def test_register_gets_one_planet(client) -> None:
    r = await client.post(
        "/auth/register",
        json={"username": "carol", "email": "carol@example.com", "password": "secret1"},
    )
    assert r.status_code == 201

    r = await client.post(
        "/auth/login",
        data={"username": "carol", "password": "secret1"},
    )
    token = r.json()["access_token"]

    r = await client.get("/planets", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    planets = r.json()
    assert len(planets) == 1
    p = planets[0]
    assert 4 <= p["position"] <= 12
    assert p["resources_metal"] == 500.0
