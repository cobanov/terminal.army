"""Defense API: list defenses on a planet, queue defense construction."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.deps import CurrentUser, DBSession
from backend.app.game.constants import (
    DEFENSE_LABELS,
    DEFENSE_PREREQUISITES,
    DEFENSE_STATS,
    BuildingType,
    DefenseType,
    TechType,
)
from backend.app.game.formulas import build_time_seconds
from backend.app.models.building import Building
from backend.app.models.planet import Planet
from backend.app.models.research import Research
from backend.app.models.ship import PlanetDefense
from backend.app.models.universe import Universe
from backend.app.services.defense_service import UNIQUE_DEFENSES, queue_defense_build

router = APIRouter(tags=["defense"])


class DefenseRow(BaseModel):
    defense_type: str
    label: str
    count: int
    cost_metal: int
    cost_crystal: int
    cost_deuterium: int
    structural_integrity: int
    shield_power: int
    weapon_power: int
    build_seconds: int
    unique: bool
    prereq_met: bool
    prereq_missing: list[str]


class DefensesResponse(BaseModel):
    planet_id: int
    shipyard_level: int
    defenses: list[DefenseRow]


@router.get("/planets/{planet_id}/defenses", response_model=DefensesResponse)
async def list_defenses(
    planet_id: int, user: CurrentUser, db: DBSession
) -> DefensesResponse:
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

    stock_res = await db.execute(
        select(PlanetDefense).where(PlanetDefense.planet_id == planet_id)
    )
    stock = {r.defense_type: r.count for r in stock_res.scalars().all()}

    rows: list[DefenseRow] = []
    for dt in DefenseType:
        m, c, d, hull, shield, weapon = DEFENSE_STATS[dt]
        per_unit_seconds = build_time_seconds(m, c, shipyard_lvl, nanite_lvl, speed)
        reqs = DEFENSE_PREREQUISITES.get(dt, {})
        missing: list[str] = []
        for k, v in reqs.items():
            if k == "shipyard":
                if shipyard_lvl < v:
                    missing.append(f"Shipyard L{v}")
            else:
                if techs.get(k, 0) < v:
                    missing.append(f"{k} L{v}")
        rows.append(DefenseRow(
            defense_type=dt.value,
            label=DEFENSE_LABELS[dt],
            count=stock.get(dt.value, 0),
            cost_metal=m, cost_crystal=c, cost_deuterium=d,
            structural_integrity=hull, shield_power=shield, weapon_power=weapon,
            build_seconds=per_unit_seconds,
            unique=dt in UNIQUE_DEFENSES,
            prereq_met=len(missing) == 0,
            prereq_missing=missing,
        ))

    return DefensesResponse(
        planet_id=planet_id, shipyard_level=shipyard_lvl, defenses=rows
    )


class BuildDefenseRequest(BaseModel):
    count: int = 1


class BuildDefenseResponse(BaseModel):
    queue_id: int
    defense_type: str
    count: int
    finished_at: str
    cost_metal: int
    cost_crystal: int
    cost_deuterium: int


@router.post(
    "/planets/{planet_id}/defense/build/{defense_type}",
    response_model=BuildDefenseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def build_defense(
    planet_id: int,
    defense_type: str,
    body: BuildDefenseRequest,
    user: CurrentUser,
    db: DBSession,
) -> BuildDefenseResponse:
    try:
        dt = DefenseType(defense_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unknown defense: {exc}") from exc

    queue = await queue_defense_build(db, planet_id, user.id, dt, body.count)
    return BuildDefenseResponse(
        queue_id=queue.id,
        defense_type=queue.item_key,
        count=queue.target_level,
        finished_at=queue.finished_at.isoformat(),
        cost_metal=queue.cost_metal,
        cost_crystal=queue.cost_crystal,
        cost_deuterium=queue.cost_deuterium,
    )
