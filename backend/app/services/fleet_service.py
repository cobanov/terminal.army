"""Fleet send/return/combat orchestration."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.game.constants import (
    BUILDING_LABELS,
    DEFENSE_LABELS,
    SHIP_LABELS,
    SHIP_STATS,
    BuildingType,
    DefenseType,
    ShipType,
    TechType,
)
from backend.app.game.fleet import (
    build_units_from_defenses,
    build_units_from_ships,
    counter_espionage_chance,
    distance,
    espionage_info_level,
    fleet_cargo_capacity,
    fleet_fuel_consumption,
    flight_duration_seconds,
    simulate_combat,
    slowest_ship_speed,
)
from backend.app.models.building import Building
from backend.app.models.fleet import Fleet, FleetMission, FleetShip, FleetStatus
from backend.app.models.planet import Planet
from backend.app.models.report import Report, ReportType
from backend.app.models.research import Research
from backend.app.models.ship import PlanetDefense, PlanetShip
from backend.app.models.universe import Universe
from backend.app.models.user import User
from backend.app.services.resource_service import refresh_planet_resources


async def _get_planet_ships(db: AsyncSession, planet_id: int) -> dict[ShipType, int]:
    res = await db.execute(select(PlanetShip).where(PlanetShip.planet_id == planet_id))
    out: dict[ShipType, int] = {}
    for r in res.scalars().all():
        try:
            out[ShipType(r.ship_type)] = r.count
        except ValueError:
            continue
    return out


async def _get_planet_defenses(db: AsyncSession, planet_id: int) -> dict[DefenseType, int]:
    res = await db.execute(select(PlanetDefense).where(PlanetDefense.planet_id == planet_id))
    out: dict[DefenseType, int] = {}
    for r in res.scalars().all():
        try:
            out[DefenseType(r.defense_type)] = r.count
        except ValueError:
            continue
    return out


async def _user_techs(db: AsyncSession, user_id: int) -> dict[TechType, int]:
    res = await db.execute(select(Research).where(Research.user_id == user_id))
    out: dict[TechType, int] = {}
    for r in res.scalars().all():
        try:
            out[TechType(r.tech_type)] = r.level
        except ValueError:
            continue
    return out


async def _user_buildings_max(db: AsyncSession, user_id: int) -> dict[str, int]:
    """For espionage reports: max of each building type across all user's planets."""
    res = await db.execute(
        select(Building.building_type, Building.level)
        .join(Planet, Planet.id == Building.planet_id)
        .where(Planet.owner_user_id == user_id)
    )
    levels: dict[str, int] = {}
    for bt, lvl in res.all():
        if lvl > levels.get(bt, 0):
            levels[bt] = lvl
    return levels


async def send_fleet(
    db: AsyncSession,
    user_id: int,
    origin_planet_id: int,
    mission: FleetMission,
    target_galaxy: int,
    target_system: int,
    target_position: int,
    ships: dict[ShipType, int],
    cargo_metal: int = 0,
    cargo_crystal: int = 0,
    cargo_deuterium: int = 0,
    speed_percent: int = 100,
) -> Fleet:
    if not ships or all(c <= 0 for c in ships.values()):
        raise HTTPException(status_code=400, detail="select at least one ship")

    planet = await db.get(Planet, origin_planet_id)
    if planet is None or planet.owner_user_id != user_id:
        raise HTTPException(status_code=404, detail="planet not found")

    if not (1 <= target_galaxy and 1 <= target_system and 1 <= target_position <= 15):
        raise HTTPException(status_code=400, detail="invalid target coords")

    await refresh_planet_resources(db, origin_planet_id)
    await db.refresh(planet)

    # Lock ship rows so two concurrent send-fleet calls can't both pass the
    # stock check and double-spend the same units.
    await db.execute(
        select(PlanetShip).where(PlanetShip.planet_id == origin_planet_id).with_for_update()
    )

    # Verify ship stock
    stock = await _get_planet_ships(db, origin_planet_id)
    for st, c in ships.items():
        if c < 0:
            raise HTTPException(status_code=400, detail=f"negative ship count: {st.value}")
        if c > 0 and stock.get(st, 0) < c:
            raise HTTPException(
                status_code=400,
                detail=f"not enough {st.value}: have {stock.get(st, 0)}, need {c}",
            )

    # Mission-specific constraints
    if mission == FleetMission.ESPIONAGE and ships.get(ShipType.ESPIONAGE_PROBE, 0) <= 0:
        raise HTTPException(status_code=400, detail="espionage requires probes")
    if mission == FleetMission.COLONIZE and ships.get(ShipType.COLONY_SHIP, 0) <= 0:
        raise HTTPException(status_code=400, detail="colonize requires a colony ship")
    if mission == FleetMission.RECYCLE and ships.get(ShipType.RECYCLER, 0) <= 0:
        raise HTTPException(status_code=400, detail="recycle requires recyclers")

    # Cargo capacity check
    cap = fleet_cargo_capacity(ships)
    total_cargo = cargo_metal + cargo_crystal + cargo_deuterium
    if total_cargo > cap:
        raise HTTPException(
            status_code=400,
            detail=f"cargo {total_cargo} exceeds capacity {cap}",
        )

    # Resource availability
    if (
        planet.resources_metal < cargo_metal
        or planet.resources_crystal < cargo_crystal
        or planet.resources_deuterium < cargo_deuterium
    ):
        raise HTTPException(status_code=400, detail="insufficient resources for cargo")

    # Distance + duration + fuel
    techs = await _user_techs(db, user_id)
    dist = distance(
        planet.galaxy, planet.system, planet.position,
        target_galaxy, target_system, target_position,
    )
    speed = slowest_ship_speed(ships, techs)
    universe = await db.get(Universe, planet.universe_id)
    u_fleet = universe.speed_fleet if universe else 1
    duration_s = flight_duration_seconds(dist, speed, u_fleet, speed_percent)
    fuel = fleet_fuel_consumption(ships, dist, duration_s, techs, speed_percent)

    if planet.resources_deuterium < cargo_deuterium + fuel:
        raise HTTPException(
            status_code=400,
            detail=f"not enough deuterium for fuel ({fuel}) + cargo ({cargo_deuterium})",
        )

    # Determine target planet (if exists) - for combat / espionage
    tgt = await db.execute(
        select(Planet).where(
            Planet.universe_id == planet.universe_id,
            Planet.galaxy == target_galaxy,
            Planet.system == target_system,
            Planet.position == target_position,
        )
    )
    target_planet = tgt.scalar_one_or_none()

    # Mission validation
    if mission == FleetMission.ATTACK:
        if target_planet is None:
            raise HTTPException(status_code=400, detail="no planet at target")
        if target_planet.owner_user_id == user_id:
            raise HTTPException(status_code=400, detail="cannot attack your own planet")
    if mission == FleetMission.TRANSPORT and target_planet is None:
        raise HTTPException(status_code=400, detail="no planet at target")
    if mission == FleetMission.ESPIONAGE and target_planet is None:
        raise HTTPException(status_code=400, detail="no planet at target")

    # Deduct stock + resources
    for st, c in ships.items():
        if c <= 0:
            continue
        row = await db.execute(
            select(PlanetShip).where(
                PlanetShip.planet_id == origin_planet_id,
                PlanetShip.ship_type == st.value,
            )
        )
        row = row.scalar_one()
        row.count -= c

    planet.resources_metal = float(planet.resources_metal) - cargo_metal
    planet.resources_crystal = float(planet.resources_crystal) - cargo_crystal
    planet.resources_deuterium = float(planet.resources_deuterium) - (cargo_deuterium + fuel)

    now = datetime.now(UTC)
    arrival = now + timedelta(seconds=duration_s)
    return_at = arrival + timedelta(seconds=duration_s) if mission != FleetMission.DEPLOY else None

    fleet = Fleet(
        owner_id=user_id,
        origin_planet_id=origin_planet_id,
        mission=mission.value,
        status=FleetStatus.OUTBOUND.value,
        universe_id=planet.universe_id,
        target_galaxy=target_galaxy,
        target_system=target_system,
        target_position=target_position,
        target_planet_id=target_planet.id if target_planet else None,
        speed_percent=speed_percent,
        departure_at=now,
        arrival_at=arrival,
        return_at=return_at,
        cargo_metal=cargo_metal,
        cargo_crystal=cargo_crystal,
        cargo_deuterium=cargo_deuterium,
        fuel_cost=fuel,
    )
    db.add(fleet)
    await db.flush()

    for st, c in ships.items():
        if c <= 0:
            continue
        db.add(FleetShip(fleet_id=fleet.id, ship_type=st.value, count=c))

    await db.commit()
    await db.refresh(fleet)
    return fleet


# ---------- Scheduler: arrivals + returns + combat ------------------------

async def process_fleet_arrivals(db: AsyncSession, now: datetime | None = None) -> int:
    """Find outbound fleets whose arrival_at has passed and process them."""
    now = now or datetime.now(UTC)
    res = await db.execute(
        select(Fleet).where(
            Fleet.status == FleetStatus.OUTBOUND.value,
            Fleet.arrival_processed.is_(False),
            Fleet.arrival_at <= now,
        )
    )
    fleets = res.scalars().all()
    processed = 0
    for fleet in fleets:
        try:
            await _process_arrival(db, fleet)
        except Exception:
            # log but don't crash scheduler
            continue
        processed += 1
    if processed:
        await db.commit()
    return processed


async def process_fleet_returns(db: AsyncSession, now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    res = await db.execute(
        select(Fleet).where(
            Fleet.status == FleetStatus.RETURNING.value,
            Fleet.return_processed.is_(False),
            Fleet.return_at != None,  # noqa: E711
            Fleet.return_at <= now,
        )
    )
    fleets = res.scalars().all()
    processed = 0
    for fleet in fleets:
        try:
            await _process_return(db, fleet)
        except Exception:
            continue
        processed += 1
    if processed:
        await db.commit()
    return processed


async def _get_fleet_ships(db: AsyncSession, fleet_id: int) -> dict[ShipType, int]:
    res = await db.execute(select(FleetShip).where(FleetShip.fleet_id == fleet_id))
    out: dict[ShipType, int] = {}
    for r in res.scalars().all():
        try:
            out[ShipType(r.ship_type)] = r.count
        except ValueError:
            continue
    return out


async def _process_arrival(db: AsyncSession, fleet: Fleet) -> None:
    """Execute arrival logic based on mission type."""
    mission = FleetMission(fleet.mission)

    if mission == FleetMission.ESPIONAGE:
        await _do_espionage(db, fleet)
        # Probes return (if any survived)
    elif mission == FleetMission.ATTACK:
        await _do_attack(db, fleet)
    elif mission == FleetMission.TRANSPORT:
        await _do_transport(db, fleet)
    elif mission == FleetMission.DEPLOY:
        await _do_deploy(db, fleet)
    elif mission == FleetMission.COLONIZE:
        await _do_colonize(db, fleet)
    # RECYCLE: post-MVP (debris field collection)

    fleet.arrival_processed = True
    if mission == FleetMission.DEPLOY or fleet.status == FleetStatus.DESTROYED.value:
        # No return phase
        fleet.status = (
            FleetStatus.DESTROYED.value
            if fleet.status == FleetStatus.DESTROYED.value
            else FleetStatus.COMPLETED.value
        )
    else:
        fleet.status = FleetStatus.RETURNING.value


async def _process_return(db: AsyncSession, fleet: Fleet) -> None:
    """Return surviving ships + any cargo (incl. plunder) to origin."""
    origin = await db.get(Planet, fleet.origin_planet_id)
    if origin is None:
        fleet.return_processed = True
        fleet.status = FleetStatus.COMPLETED.value
        return

    # Ships back into stock
    fleet_ships = await _get_fleet_ships(db, fleet.id)
    for st, c in fleet_ships.items():
        if c <= 0:
            continue
        row = await db.execute(
            select(PlanetShip).where(
                PlanetShip.planet_id == origin.id,
                PlanetShip.ship_type == st.value,
            )
        )
        ps = row.scalar_one_or_none()
        if ps is None:
            ps = PlanetShip(planet_id=origin.id, ship_type=st.value, count=0)
            db.add(ps)
            await db.flush()
        ps.count += c

    # Cargo back to origin
    origin.resources_metal = float(origin.resources_metal) + fleet.cargo_metal
    origin.resources_crystal = float(origin.resources_crystal) + fleet.cargo_crystal
    origin.resources_deuterium = float(origin.resources_deuterium) + fleet.cargo_deuterium

    fleet.return_processed = True
    fleet.status = FleetStatus.COMPLETED.value


# ---------- Mission handlers ---------------------------------------------

async def _do_transport(db: AsyncSession, fleet: Fleet) -> None:
    """Drop cargo at target, ships return empty."""
    target = await db.get(Planet, fleet.target_planet_id) if fleet.target_planet_id else None
    if target is not None:
        target.resources_metal = float(target.resources_metal) + fleet.cargo_metal
        target.resources_crystal = float(target.resources_crystal) + fleet.cargo_crystal
        target.resources_deuterium = float(target.resources_deuterium) + fleet.cargo_deuterium
    fleet.cargo_metal = 0
    fleet.cargo_crystal = 0
    fleet.cargo_deuterium = 0


async def _do_deploy(db: AsyncSession, fleet: Fleet) -> None:
    """Ships stay at target (must be own planet)."""
    if fleet.target_planet_id is None:
        return
    target = await db.get(Planet, fleet.target_planet_id)
    if target is None or target.owner_user_id != fleet.owner_id:
        # Invalid deploy: cancel and return as normal
        return

    # Move ships to target stock
    fleet_ships = await _get_fleet_ships(db, fleet.id)
    for st, c in fleet_ships.items():
        if c <= 0:
            continue
        row = await db.execute(
            select(PlanetShip).where(
                PlanetShip.planet_id == target.id,
                PlanetShip.ship_type == st.value,
            )
        )
        ps = row.scalar_one_or_none()
        if ps is None:
            ps = PlanetShip(planet_id=target.id, ship_type=st.value, count=0)
            db.add(ps)
            await db.flush()
        ps.count += c
    # Cargo also dropped
    target.resources_metal = float(target.resources_metal) + fleet.cargo_metal
    target.resources_crystal = float(target.resources_crystal) + fleet.cargo_crystal
    target.resources_deuterium = float(target.resources_deuterium) + fleet.cargo_deuterium
    # Zero out fleet
    res = await db.execute(select(FleetShip).where(FleetShip.fleet_id == fleet.id))
    for fs in res.scalars().all():
        fs.count = 0
    fleet.cargo_metal = 0
    fleet.cargo_crystal = 0
    fleet.cargo_deuterium = 0


async def _do_colonize(db: AsyncSession, fleet: Fleet) -> None:
    """Try to plant a colony at the target. Faz 11 - placeholder."""
    # Not implemented in MVP scope. Ships return.
    pass


async def _do_espionage(db: AsyncSession, fleet: Fleet) -> None:
    """Generate an espionage report on target. Probes may be destroyed (counter-esp)."""
    if fleet.target_planet_id is None:
        return
    target = await db.get(Planet, fleet.target_planet_id)
    if target is None:
        return
    attacker = await db.get(User, fleet.owner_id)
    target_owner = await db.get(User, target.owner_user_id)
    if attacker is None or target_owner is None:
        return

    # Fetch fleet probes
    fs_res = await db.execute(
        select(FleetShip).where(
            FleetShip.fleet_id == fleet.id,
            FleetShip.ship_type == ShipType.ESPIONAGE_PROBE.value,
        )
    )
    probe_row = fs_res.scalar_one_or_none()
    probes = probe_row.count if probe_row else 0
    if probes <= 0:
        return

    # Get tech levels
    attacker_techs = await _user_techs(db, attacker.id)
    target_techs = await _user_techs(db, target_owner.id)
    atk_esp = attacker_techs.get(TechType.ESPIONAGE, 0)
    def_esp = target_techs.get(TechType.ESPIONAGE, 0)

    info_level = espionage_info_level(probes, atk_esp, def_esp)
    counter_chance = counter_espionage_chance(probes, def_esp, atk_esp)

    # Possibly destroy some probes (counter-esp)
    import random
    destroyed_probes = 0
    for _ in range(probes):
        if random.random() < counter_chance:
            destroyed_probes += 1
    if destroyed_probes > 0 and probe_row is not None:
        probe_row.count = max(0, probe_row.count - destroyed_probes)

    # Build report body (JSON)
    await refresh_planet_resources(db, target.id)
    await db.refresh(target)

    body: dict = {
        "info_level": info_level,
        "probes_sent": probes,
        "probes_destroyed": destroyed_probes,
        "target_owner": target_owner.username,
        "target_coord": f"{target.galaxy}:{target.system}:{target.position}",
        "target_name": target.name,
        "resources": {
            "metal": int(target.resources_metal),
            "crystal": int(target.resources_crystal),
            "deuterium": int(target.resources_deuterium),
        },
    }

    # Level 2+: fleet (target's ships at planet)
    if info_level >= 2:
        target_ships = await _get_planet_ships(db, target.id)
        body["fleet"] = {k.value: v for k, v in target_ships.items() if v > 0}

    # Level 3+: defenses
    if info_level >= 3:
        target_defs = await _get_planet_defenses(db, target.id)
        body["defenses"] = {k.value: v for k, v in target_defs.items() if v > 0}

    # Level 4+: buildings
    if info_level >= 4:
        bld_res = await db.execute(
            select(Building).where(Building.planet_id == target.id)
        )
        body["buildings"] = {b.building_type: b.level for b in bld_res.scalars().all()}

    # Level 5: research
    if info_level >= 5:
        body["research"] = {k.value: v for k, v in target_techs.items() if v > 0}

    report = Report(
        owner_id=attacker.id,
        report_type=ReportType.ESPIONAGE.value,
        title=f"Espionage on {target.galaxy}:{target.system}:{target.position} ({target_owner.username})",
        body=json.dumps(body, ensure_ascii=False),
        target_galaxy=target.galaxy,
        target_system=target.system,
        target_position=target.position,
    )
    db.add(report)

    # Also: notify defender of being spied on (level 1 report for them)
    notify = Report(
        owner_id=target_owner.id,
        report_type=ReportType.ESPIONAGE.value,
        title=f"Spied on by {attacker.username} from {fleet.target_galaxy}:{fleet.target_system}:{fleet.target_position}",
        body=json.dumps({
            "info_level": 1,
            "spy_username": attacker.username,
            "probes_sent": probes,
            "probes_destroyed": destroyed_probes,
            "counter_chance": round(counter_chance, 2),
        }, ensure_ascii=False),
        target_galaxy=target.galaxy,
        target_system=target.system,
        target_position=target.position,
    )
    db.add(notify)


async def _do_attack(db: AsyncSession, fleet: Fleet) -> None:
    """Single-round combat simulator."""
    if fleet.target_planet_id is None:
        return
    target = await db.get(Planet, fleet.target_planet_id)
    if target is None:
        return
    attacker = await db.get(User, fleet.owner_id)
    target_owner = await db.get(User, target.owner_user_id)
    if attacker is None or target_owner is None:
        return

    attacker_techs = await _user_techs(db, attacker.id)
    target_techs = await _user_techs(db, target_owner.id)

    # Attacker fleet -> CombatUnits
    fleet_ships = await _get_fleet_ships(db, fleet.id)
    atk_units = build_units_from_ships(
        fleet_ships,
        weapons=attacker_techs.get(TechType.WEAPONS, 0),
        shielding=attacker_techs.get(TechType.SHIELDING, 0),
        armour=attacker_techs.get(TechType.ARMOUR, 0),
    )

    # Defender stationary ships + defenses
    def_ships = await _get_planet_ships(db, target.id)
    def_units = build_units_from_ships(
        def_ships,
        weapons=target_techs.get(TechType.WEAPONS, 0),
        shielding=target_techs.get(TechType.SHIELDING, 0),
        armour=target_techs.get(TechType.ARMOUR, 0),
    )
    def_defenses = await _get_planet_defenses(db, target.id)
    def_def_units = build_units_from_defenses(
        def_defenses,
        weapons=target_techs.get(TechType.WEAPONS, 0),
        shielding=target_techs.get(TechType.SHIELDING, 0),
        armour=target_techs.get(TechType.ARMOUR, 0),
    )

    result = simulate_combat(atk_units, def_units, def_def_units)

    # Update DB counts
    # Attacker fleet remaining
    for fs in (await db.execute(select(FleetShip).where(FleetShip.fleet_id == fleet.id))).scalars().all():
        new_count = result.attacker_remaining.get(fs.ship_type, fs.count)
        fs.count = max(0, new_count)
    total_atk_remaining = sum(result.attacker_remaining.values())
    if total_atk_remaining == 0:
        fleet.status = FleetStatus.DESTROYED.value

    # Defender ships
    for ps in (await db.execute(select(PlanetShip).where(PlanetShip.planet_id == target.id))).scalars().all():
        if ps.ship_type in result.defender_ships_remaining:
            ps.count = max(0, result.defender_ships_remaining[ps.ship_type])
    # Defender defenses
    for pd in (await db.execute(select(PlanetDefense).where(PlanetDefense.planet_id == target.id))).scalars().all():
        if pd.defense_type in result.defender_defenses_remaining:
            pd.count = max(0, result.defender_defenses_remaining[pd.defense_type])

    # Plunder if attacker won and survives
    plunder_metal = plunder_crystal = plunder_deut = 0
    if result.winner == "attacker" and fleet.status != FleetStatus.DESTROYED.value:
        await refresh_planet_resources(db, target.id)
        await db.refresh(target)
        plunder_cap = fleet_cargo_capacity({
            ShipType(st): c for st, c in result.attacker_remaining.items() if c > 0
        }) - (fleet.cargo_metal + fleet.cargo_crystal + fleet.cargo_deuterium)
        plunder_cap = max(0, plunder_cap)
        max_share = 0.5
        m_plund = min(int(target.resources_metal * max_share), plunder_cap // 3)
        c_plund = min(int(target.resources_crystal * max_share), plunder_cap // 3)
        d_plund = min(int(target.resources_deuterium * max_share), plunder_cap - m_plund - c_plund)
        fleet.cargo_metal += m_plund
        fleet.cargo_crystal += c_plund
        fleet.cargo_deuterium += d_plund
        target.resources_metal = float(target.resources_metal) - m_plund
        target.resources_crystal = float(target.resources_crystal) - c_plund
        target.resources_deuterium = float(target.resources_deuterium) - d_plund
        plunder_metal, plunder_crystal, plunder_deut = m_plund, c_plund, d_plund

    # Generate reports (one for each side)
    coord = f"{target.galaxy}:{target.system}:{target.position}"
    body = {
        "attacker": attacker.username,
        "defender": target_owner.username,
        "target_coord": coord,
        "winner": result.winner,
        "attacker_attack": result.attacker_total_attack,
        "defender_attack": result.defender_total_attack,
        "attacker_destroyed": result.attacker_destroyed,
        "defender_ships_destroyed": result.defender_ships_destroyed,
        "defender_defenses_destroyed": result.defender_defenses_destroyed,
        "plunder": {
            "metal": plunder_metal,
            "crystal": plunder_crystal,
            "deuterium": plunder_deut,
        },
        "debris": {
            "metal": result.debris_metal,
            "crystal": result.debris_crystal,
        },
    }
    body_json = json.dumps(body, ensure_ascii=False)

    for owner in (attacker.id, target_owner.id):
        rep = Report(
            owner_id=owner,
            report_type=ReportType.COMBAT.value,
            title=f"Combat at {coord}: {result.winner.upper()}",
            body=body_json,
            target_galaxy=target.galaxy,
            target_system=target.system,
            target_position=target.position,
        )
        db.add(rep)
