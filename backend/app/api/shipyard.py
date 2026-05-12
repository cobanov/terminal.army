"""Shipyard: list ships/defenses, build ships."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.deps import CurrentUser, DBSession
from backend.app.game.constants import (
    SHIP_LABELS,
    SHIP_PREREQUISITES,
    SHIP_STATS,
    BuildingType,
    ShipType,
)
from backend.app.game.formulas import build_time_seconds
from backend.app.models.building import Building
from backend.app.models.planet import Planet
from backend.app.models.research import Research
from backend.app.models.ship import PlanetShip
from backend.app.models.universe import Universe
from backend.app.rate_limit import limiter
from backend.app.services.shipyard_service import queue_ship_build

router = APIRouter(tags=["shipyard"])


class ShipRow(BaseModel):
    ship_type: str
    label: str
    count: int
    cost_metal: int
    cost_crystal: int
    cost_deuterium: int
    build_seconds: int  # per-ship at current shipyard/nanite level
    prereq_met: bool
    prereq_missing: list[str]


class ShipsResponse(BaseModel):
    planet_id: int
    shipyard_level: int
    ships: list[ShipRow]


@router.get("/planets/{planet_id}/ships", response_model=ShipsResponse)
async def list_ships(planet_id: int, user: CurrentUser, db: DBSession) -> ShipsResponse:
    planet = await db.get(Planet, planet_id)
    if planet is None or planet.owner_user_id != user.id:
        raise HTTPException(status_code=404, detail="planet not found")

    universe = await db.get(Universe, planet.universe_id)
    speed = float(universe.speed_economy) if universe else 1.0

    bld_res = await db.execute(select(Building).where(Building.planet_id == planet_id))
    bld = {b.building_type: b.level for b in bld_res.scalars().all()}
    shipyard_lvl = bld.get(BuildingType.SHIPYARD.value, 0)
    nanite_lvl = bld.get(BuildingType.NANITE_FACTORY.value, 0)

    tech_res = await db.execute(select(Research).where(Research.user_id == user.id))
    techs = {r.tech_type: r.level for r in tech_res.scalars().all()}

    stock_res = await db.execute(select(PlanetShip).where(PlanetShip.planet_id == planet_id))
    stock = {r.ship_type: r.count for r in stock_res.scalars().all()}

    rows: list[ShipRow] = []
    for st in ShipType:
        m, c, d, *_ = SHIP_STATS[st]
        per_ship_seconds = build_time_seconds(m, c, shipyard_lvl, nanite_lvl, speed)
        reqs = SHIP_PREREQUISITES.get(st, {})
        missing = []
        for k, v in reqs.items():
            if k == "shipyard":
                if shipyard_lvl < v:
                    missing.append(f"Shipyard L{v}")
            else:
                if techs.get(k, 0) < v:
                    missing.append(f"{k} L{v}")
        rows.append(
            ShipRow(
                ship_type=st.value,
                label=SHIP_LABELS[st],
                count=stock.get(st.value, 0),
                cost_metal=m,
                cost_crystal=c,
                cost_deuterium=d,
                build_seconds=per_ship_seconds,
                prereq_met=len(missing) == 0,
                prereq_missing=missing,
            )
        )

    return ShipsResponse(planet_id=planet_id, shipyard_level=shipyard_lvl, ships=rows)


class BuildShipRequest(BaseModel):
    count: int = 1


class BuildShipResponse(BaseModel):
    queue_id: int
    ship_type: str
    count: int
    finished_at: str
    cost_metal: int
    cost_crystal: int
    cost_deuterium: int


@router.post(
    "/planets/{planet_id}/shipyard/build/{ship_type}",
    response_model=BuildShipResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("60/minute")
async def build_ship(
    request: Request,
    planet_id: int,
    ship_type: str,
    body: BuildShipRequest,
    user: CurrentUser,
    db: DBSession,
) -> BuildShipResponse:
    try:
        st = ShipType(ship_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unknown ship: {exc}") from exc

    queue = await queue_ship_build(db, planet_id, user.id, st, body.count)
    return BuildShipResponse(
        queue_id=queue.id,
        ship_type=queue.item_key,
        count=queue.target_level,  # field reused for count in SHIP queues
        finished_at=queue.finished_at.isoformat(),
        cost_metal=queue.cost_metal,
        cost_crystal=queue.cost_crystal,
        cost_deuterium=queue.cost_deuterium,
    )
