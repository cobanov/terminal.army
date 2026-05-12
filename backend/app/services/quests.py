"""Onboarding quest list.

A linear set of milestones designed to teach a new player the order of
operations: mine → energy → lab → research → shipyard → ships → fleet →
defenses. Each quest is a pure predicate over the user's current state.

The list is intentionally hardcoded — these are tutorial quests, not a
content system. They should feel earned just from playing normally.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.building import Building
from backend.app.models.fleet import Fleet, FleetMission
from backend.app.models.planet import Planet
from backend.app.models.research import Research
from backend.app.models.ship import PlanetDefense, PlanetShip


@dataclass(frozen=True)
class Quest:
    id: str
    title: str
    hint: str


# Predicate returns True if the quest is satisfied.
_QUEST_DEFS: list[tuple[Quest, str, dict[str, int]]] = [
    # (Quest, kind, params)
    # kind dispatches in _check_quest below.
    (
        Quest(
            "metal_5",
            "Build Metal Mine to level 5",
            "Run /upgrade metal_mine until it hits level 5. Mine output triples each step.",
        ),
        "building_level",
        {"metal_mine": 5},
    ),
    (
        Quest(
            "crystal_3",
            "Build Crystal Mine to level 3",
            "Run /upgrade crystal_mine three times. Crystal gates most research.",
        ),
        "building_level",
        {"crystal_mine": 3},
    ),
    (
        Quest(
            "solar_5",
            "Build Solar Plant to level 5",
            "Mines stall without energy. /upgrade solar_plant — check the topbar's E indicator.",
        ),
        "building_level",
        {"solar_plant": 5},
    ),
    (
        Quest(
            "deut_3",
            "Build Deuterium Synthesizer to level 3",
            "Fleets burn deuterium for fuel. /upgrade deuterium_synthesizer 3 times.",
        ),
        "building_level",
        {"deuterium_synthesizer": 3},
    ),
    (
        Quest(
            "robotics_2",
            "Build Robotics Factory to level 2",
            "Speeds up every build. /upgrade robotics_factory twice.",
        ),
        "building_level",
        {"robotics_factory": 2},
    ),
    (
        Quest(
            "lab_1",
            "Build Research Lab",
            "Required for any tech. /upgrade research_lab to level 1.",
        ),
        "building_level",
        {"research_lab": 1},
    ),
    (
        Quest(
            "energy_2",
            "Research Energy Technology to level 2",
            "First research milestone. /research energy twice.",
        ),
        "tech_level",
        {"energy": 2},
    ),
    (
        Quest(
            "shipyard_2",
            "Build Shipyard to level 2",
            "Unlocks ships and defenses. /upgrade shipyard twice.",
        ),
        "building_level",
        {"shipyard": 2},
    ),
    (
        Quest(
            "combustion_1",
            "Research Combustion Drive",
            "Unlocks the Small Cargo. /research combustion_drive.",
        ),
        "tech_level",
        {"combustion_drive": 1},
    ),
    (
        Quest(
            "small_cargo", "Build your first Small Cargo", "/build small_cargo 1 — your first ship."
        ),
        "ship_count",
        {"small_cargo": 1},
    ),
    (
        Quest(
            "first_fleet",
            "Send your first fleet",
            "/transport <coord> or /attack <coord> — anything that leaves the planet counts.",
        ),
        "fleet_sent",
        {},
    ),
    (
        Quest(
            "first_defense",
            "Build your first defense unit",
            "Even one rocket launcher discourages farming. /defend rocket_launcher 1.",
        ),
        "defense_count",
        {"rocket_launcher": 1},
    ),
    (
        Quest(
            "espionage_1",
            "Research Espionage to level 1",
            "/research espionage. Unlocks probe-scouting.",
        ),
        "tech_level",
        {"espionage": 1},
    ),
    (
        Quest(
            "probe_built",
            "Build an Espionage Probe",
            "/build espionage_probe 1 — costs almost nothing.",
        ),
        "ship_count",
        {"espionage_probe": 1},
    ),
    (
        Quest(
            "scout_someone",
            "Send a probe to scout another planet",
            "/espionage <g>:<s>:<p> — pick a target from /galaxy.",
        ),
        "fleet_sent_mission",
        {"espionage": 1},
    ),
]


async def _max_building_level(db: AsyncSession, user_id: int, bt: str) -> int:
    res = await db.execute(
        select(func.max(Building.level))
        .join(Planet, Planet.id == Building.planet_id)
        .where(Planet.owner_user_id == user_id, Building.building_type == bt)
    )
    return int(res.scalar() or 0)


async def _tech_level(db: AsyncSession, user_id: int, tt: str) -> int:
    res = await db.execute(
        select(Research.level).where(Research.user_id == user_id, Research.tech_type == tt)
    )
    return int(res.scalar() or 0)


async def _ship_total(db: AsyncSession, user_id: int, st: str) -> int:
    res = await db.execute(
        select(func.sum(PlanetShip.count))
        .join(Planet, Planet.id == PlanetShip.planet_id)
        .where(Planet.owner_user_id == user_id, PlanetShip.ship_type == st)
    )
    return int(res.scalar() or 0)


async def _defense_total(db: AsyncSession, user_id: int, dt: str) -> int:
    res = await db.execute(
        select(func.sum(PlanetDefense.count))
        .join(Planet, Planet.id == PlanetDefense.planet_id)
        .where(Planet.owner_user_id == user_id, PlanetDefense.defense_type == dt)
    )
    return int(res.scalar() or 0)


async def _fleet_sent_total(db: AsyncSession, user_id: int) -> int:
    res = await db.execute(select(func.count()).select_from(Fleet).where(Fleet.owner_id == user_id))
    return int(res.scalar() or 0)


async def _fleet_mission_total(db: AsyncSession, user_id: int, mission: str) -> int:
    res = await db.execute(
        select(func.count())
        .select_from(Fleet)
        .where(Fleet.owner_id == user_id, Fleet.mission == mission)
    )
    return int(res.scalar() or 0)


async def _check_quest(db: AsyncSession, user_id: int, kind: str, params: dict[str, int]) -> bool:
    if kind == "building_level":
        for bt, lvl in params.items():
            if await _max_building_level(db, user_id, bt) < lvl:
                return False
        return True
    if kind == "tech_level":
        for tt, lvl in params.items():
            if await _tech_level(db, user_id, tt) < lvl:
                return False
        return True
    if kind == "ship_count":
        for st, c in params.items():
            if await _ship_total(db, user_id, st) < c:
                return False
        return True
    if kind == "defense_count":
        for dt, c in params.items():
            if await _defense_total(db, user_id, dt) < c:
                return False
        return True
    if kind == "fleet_sent":
        return await _fleet_sent_total(db, user_id) >= 1
    if kind == "fleet_sent_mission":
        for m, c in params.items():
            try:
                FleetMission(m)
            except ValueError:
                return False
            if await _fleet_mission_total(db, user_id, m) < c:
                return False
        return True
    return False


async def user_quest_status(db: AsyncSession, user_id: int) -> dict:
    """Return {completed: [...], current: Quest | None, total: int}."""
    completed: list[Quest] = []
    current: Quest | None = None
    for quest, kind, params in _QUEST_DEFS:
        ok = await _check_quest(db, user_id, kind, params)
        if ok:
            completed.append(quest)
        else:
            current = quest
            break
    return {
        "completed": completed,
        "current": current,
        "total": len(_QUEST_DEFS),
        "done_count": len(completed),
    }
