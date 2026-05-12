"""Compute leaderboard points.

OGame-style: points = total resources invested in everything you've built.
Specifically:
    - Buildings: sum of cost(building_type, level) for level in 1..current
    - Research: sum of cost(tech_type, level) for level in 1..current
    - Ships: count * cost(ship_type) summed over fleet
    - Defenses: count * cost(defense_type) summed

A unit of resource = 1 point (metal + crystal + deuterium combined).

Recomputed on demand. For 1000 players this is < 100ms even with no
caching; for larger scales we can persist a `User.points` column updated
on each apply.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.game.constants import (
    DEFENSE_STATS,
    SHIP_STATS,
    BuildingType,
    DefenseType,
    ShipType,
    TechType,
)
from backend.app.game.formulas import building_cost, research_cost
from backend.app.models.building import Building
from backend.app.models.planet import Planet
from backend.app.models.research import Research
from backend.app.models.ship import PlanetDefense, PlanetShip


def _cumulative_building_cost(bt_value: str, level: int) -> int:
    """Sum of metal+crystal+deut costs from L1 through `level`."""
    if level <= 0:
        return 0
    try:
        bt = BuildingType(bt_value)
    except ValueError:
        return 0
    total = 0
    for lvl in range(1, level + 1):
        m, c, d = building_cost(bt, lvl)
        total += m + c + d
    return total


def _cumulative_research_cost(tt_value: str, level: int) -> int:
    if level <= 0:
        return 0
    try:
        tt = TechType(tt_value)
    except ValueError:
        return 0
    total = 0
    for lvl in range(1, level + 1):
        m, c, d = research_cost(tt, lvl)
        total += m + c + d
    return total


async def user_points(db: AsyncSession, user_id: int) -> dict[str, int]:
    """Return building, research, fleet, defense, total points for a user."""
    # Buildings — across all owned planets
    bld_res = await db.execute(
        select(Building.building_type, Building.level)
        .join(Planet, Planet.id == Building.planet_id)
        .where(Planet.owner_user_id == user_id)
    )
    building_points = sum(_cumulative_building_cost(bt, lvl) for bt, lvl in bld_res.all())

    # Research — per user
    res_res = await db.execute(
        select(Research.tech_type, Research.level).where(Research.user_id == user_id)
    )
    research_points = sum(_cumulative_research_cost(tt, lvl) for tt, lvl in res_res.all())

    # Fleet — ships across owned planets
    ship_res = await db.execute(
        select(PlanetShip.ship_type, PlanetShip.count)
        .join(Planet, Planet.id == PlanetShip.planet_id)
        .where(Planet.owner_user_id == user_id)
    )
    fleet_points = 0
    for st_value, count in ship_res.all():
        try:
            st = ShipType(st_value)
        except ValueError:
            continue
        m, c, d = SHIP_STATS[st][0], SHIP_STATS[st][1], SHIP_STATS[st][2]
        fleet_points += (m + c + d) * count

    # Defenses
    def_res = await db.execute(
        select(PlanetDefense.defense_type, PlanetDefense.count)
        .join(Planet, Planet.id == PlanetDefense.planet_id)
        .where(Planet.owner_user_id == user_id)
    )
    defense_points = 0
    for dt_value, count in def_res.all():
        try:
            dt = DefenseType(dt_value)
        except ValueError:
            continue
        m, c, d = DEFENSE_STATS[dt][0], DEFENSE_STATS[dt][1], DEFENSE_STATS[dt][2]
        defense_points += (m + c + d) * count

    total = building_points + research_points + fleet_points + defense_points
    return {
        "building_points": building_points,
        "research_points": research_points,
        "fleet_points": fleet_points,
        "defense_points": defense_points,
        "total_points": total,
    }
