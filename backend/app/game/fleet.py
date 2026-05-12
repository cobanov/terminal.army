"""Fleet movement formulas + simplified combat.

Source: https://ogame.fandom.com/wiki/Combat
Source: https://ogame.fandom.com/wiki/Fleet
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import floor, sqrt

from backend.app.game.constants import (
    DEFENSE_STATS,
    SHIP_DRIVE,
    SHIP_STATS,
    DefenseType,
    ShipType,
    TechType,
)


# ---------- Distance / duration / fuel -------------------------------------
def distance(
    g_from: int,
    s_from: int,
    p_from: int,
    g_to: int,
    s_to: int,
    p_to: int,
) -> int:
    """Inter-coordinate distance per OGame formula.

    - Different galaxies: 20000 * |galaxy_diff|
    - Same galaxy, different systems: 2700 + 95 * |system_diff|
    - Same system, different positions: 1000 + 5 * |pos_diff|
    - Same coords: 5
    """
    if g_from != g_to:
        return 20000 * abs(g_from - g_to)
    if s_from != s_to:
        return 2700 + 95 * abs(s_from - s_to)
    if p_from != p_to:
        return 1000 + 5 * abs(p_from - p_to)
    return 5


def ship_speed(ship: ShipType, tech_levels: dict[TechType, int]) -> int:
    """Ship speed adjusted for its drive's tech level: base * (1 + 0.1 * drive_level).

    Some ships swap drives at high levels (OGame Origin) but MVP uses base drive.
    """
    base = SHIP_STATS[ship][6]  # base_speed
    drive = SHIP_DRIVE[ship]
    lvl = tech_levels.get(drive, 0)
    # Combustion = 10% per level; Impulse = 20%; Hyperspace = 30%
    multiplier_per_level = {
        TechType.COMBUSTION_DRIVE: 0.10,
        TechType.IMPULSE_DRIVE: 0.20,
        TechType.HYPERSPACE_DRIVE: 0.30,
    }.get(drive, 0.10)
    return int(base * (1 + multiplier_per_level * lvl))


def flight_duration_seconds(
    distance_units: int,
    fleet_speed: int,
    universe_speed_fleet: int = 1,
    speed_percent: int = 100,
) -> int:
    """OGame formula: t = 10 + 3500 * sqrt((distance * 10) / fleet_speed) / fleet_speed_universe

    fleet_speed = min of all ship speeds in the fleet (slowest ship sets the pace).
    speed_percent: 10..100 (10% increments; lower % = slower + less fuel).
    """
    if fleet_speed <= 0:
        return 1
    sp = max(10, min(100, speed_percent)) / 100.0
    base = (3500.0 * sqrt(distance_units * 10.0 / fleet_speed) / fleet_speed + 10.0) / max(
        1, universe_speed_fleet
    )
    return max(1, int(base / sp))


def fleet_fuel_consumption(
    ships: dict[ShipType, int],
    distance_units: int,
    flight_time_seconds: int,
    tech_levels: dict[TechType, int] | None = None,
    speed_percent: int = 100,
) -> int:
    """Approximate fuel: sum_per_ship( fuel_base * count * dist / 35000 * (speed_factor) )

    Simplified vs full OGame formula.
    """
    if not ships:
        return 0
    sp = max(10, min(100, speed_percent)) / 100.0
    total = 0.0
    for st, count in ships.items():
        if count <= 0:
            continue
        fuel = SHIP_STATS[st][8]
        # OGame's exact formula uses fleet speed too; this is a close approximation.
        total += count * fuel * (distance_units / 35000.0) * ((0.5 + sp) ** 2)
    return max(1, int(total))


def fleet_cargo_capacity(ships: dict[ShipType, int]) -> int:
    """Total cargo capacity in resource units."""
    return sum(SHIP_STATS[st][7] * count for st, count in ships.items() if count > 0)


def slowest_ship_speed(
    ships: dict[ShipType, int],
    tech_levels: dict[TechType, int],
) -> int:
    """Min speed among ships in fleet (sets the pace)."""
    speeds = [ship_speed(st, tech_levels) for st, c in ships.items() if c > 0]
    return min(speeds) if speeds else 5000


# ---------- Espionage --------------------------------------------------------
def espionage_info_level(
    attacker_probes: int,
    attacker_espionage_tech: int,
    defender_espionage_tech: int,
) -> int:
    """How much info the report shows.

    OGame-ish: depends on probe count and tech delta.
    - 1: resources only
    - 2: + fleet
    - 3: + defense
    - 4: + buildings
    - 5: + research

    Simplified: floor(probes / 2) + max(0, atk_tech - def_tech)
    """
    delta = max(0, attacker_espionage_tech - defender_espionage_tech)
    return max(1, min(5, floor(attacker_probes / 2) + delta + 1))


def counter_espionage_chance(
    attacker_probes: int,
    defender_espionage_tech: int,
    attacker_espionage_tech: int,
) -> float:
    """Counter-espionage: defender may destroy probes (0..1 probability)."""
    if attacker_espionage_tech > defender_espionage_tech:
        return 0.0
    base = attacker_probes / 5.0
    diff = max(0, defender_espionage_tech - attacker_espionage_tech)
    return min(1.0, base * (0.05 + 0.05 * diff))


# ---------- Simplified combat -----------------------------------------------
@dataclass
class CombatUnit:
    """One unit type with stats and count, used by combat sim."""

    name: str
    count: int
    weapon: int  # base attack
    shield: int  # per-unit shield
    armor: int  # per-unit structural integrity (armor)


def _apply_tech_mods(
    base_weapon: int,
    base_shield: int,
    base_armor: int,
    weapons_tech: int,
    shielding_tech: int,
    armour_tech: int,
) -> tuple[int, int, int]:
    """OGame: each tech adds 10% per level."""
    return (
        int(base_weapon * (1 + 0.10 * weapons_tech)),
        int(base_shield * (1 + 0.10 * shielding_tech)),
        int(base_armor * (1 + 0.10 * armour_tech)),
    )


def build_units_from_ships(
    ships: dict[ShipType, int],
    weapons: int = 0,
    shielding: int = 0,
    armour: int = 0,
) -> list[CombatUnit]:
    units = []
    for st, count in ships.items():
        if count <= 0:
            continue
        m, c, d, armor, shld, atk, *_ = SHIP_STATS[st]
        atk2, shld2, armor2 = _apply_tech_mods(atk, shld, armor, weapons, shielding, armour)
        units.append(
            CombatUnit(name=st.value, count=count, weapon=atk2, shield=shld2, armor=armor2)
        )
    return units


def build_units_from_defenses(
    defenses: dict[DefenseType, int],
    weapons: int = 0,
    shielding: int = 0,
    armour: int = 0,
) -> list[CombatUnit]:
    units = []
    for dt, count in defenses.items():
        if count <= 0:
            continue
        m, c, d, armor, shld, atk = DEFENSE_STATS[dt]
        atk2, shld2, armor2 = _apply_tech_mods(atk, shld, armor, weapons, shielding, armour)
        units.append(
            CombatUnit(name=dt.value, count=count, weapon=atk2, shield=shld2, armor=armor2)
        )
    return units


@dataclass
class CombatResult:
    attacker_remaining: dict[str, int] = field(default_factory=dict)
    defender_ships_remaining: dict[str, int] = field(default_factory=dict)
    defender_defenses_remaining: dict[str, int] = field(default_factory=dict)
    attacker_destroyed: dict[str, int] = field(default_factory=dict)
    defender_ships_destroyed: dict[str, int] = field(default_factory=dict)
    defender_defenses_destroyed: dict[str, int] = field(default_factory=dict)
    attacker_total_attack: int = 0
    defender_total_attack: int = 0
    winner: str = "draw"  # "attacker" | "defender" | "draw"
    debris_metal: int = 0
    debris_crystal: int = 0


def simulate_combat(
    attacker_units: list[CombatUnit],
    defender_ship_units: list[CombatUnit],
    defender_defense_units: list[CombatUnit],
) -> CombatResult:
    """Single-round attack/defense damage application.

    Each side computes total attack and deals it to the other side, distributed
    proportionally across remaining HP (armor) of the opposing units.
    Shields absorb damage first per unit type pool (simplified).
    Casualties calculated by: damage_to_unit_pool / total_hp_unit * count.

    NOT the full OGame rapid-fire chart (that requires a much larger simulation).
    """
    res = CombatResult()

    def total_attack(units: list[CombatUnit]) -> int:
        return sum(u.count * u.weapon for u in units if u.count > 0)

    def total_hp_pool(units: list[CombatUnit]) -> int:
        # Per-unit HP = shield + armor
        return sum(u.count * (u.shield + u.armor) for u in units if u.count > 0)

    atk_attack = total_attack(attacker_units)
    def_attack = total_attack(defender_ship_units) + total_attack(defender_defense_units)
    res.attacker_total_attack = atk_attack
    res.defender_total_attack = def_attack

    # Apply attacker's damage to defenders (ships + defenses combined pool)
    def_hp = total_hp_pool(defender_ship_units) + total_hp_pool(defender_defense_units)
    atk_hp = total_hp_pool(attacker_units)

    def apply_damage(units: list[CombatUnit], total_damage: int, total_hp: int) -> dict[str, int]:
        """Returns dict of {unit_name: destroyed_count}. Mutates units' counts in place."""
        destroyed_map: dict[str, int] = {}
        if total_hp <= 0:
            return destroyed_map
        for u in units:
            if u.count <= 0:
                continue
            per_unit_hp = u.shield + u.armor
            share = (u.count * per_unit_hp) / total_hp
            damage_to_pool = int(total_damage * share)
            destroyed = min(u.count, damage_to_pool // max(1, per_unit_hp))
            destroyed_map[u.name] = destroyed
            u.count -= destroyed
        return destroyed_map

    def_destroyed = apply_damage(defender_ship_units + defender_defense_units, atk_attack, def_hp)
    atk_destroyed = apply_damage(attacker_units, def_attack, atk_hp)

    # Pack remaining
    res.attacker_remaining = {u.name: u.count for u in attacker_units}
    res.attacker_destroyed = {n: v for n, v in atk_destroyed.items() if v > 0}

    for u in defender_ship_units:
        res.defender_ships_remaining[u.name] = u.count
    for u in defender_defense_units:
        res.defender_defenses_remaining[u.name] = u.count

    # Split destroyed map back by source list
    ship_names = {u.name for u in defender_ship_units}
    def_names = {u.name for u in defender_defense_units}
    for n, v in def_destroyed.items():
        if v <= 0:
            continue
        if n in ship_names:
            res.defender_ships_destroyed[n] = v
        elif n in def_names:
            res.defender_defenses_destroyed[n] = v

    # Winner
    atk_left = sum(u.count for u in attacker_units)
    def_left = sum(u.count for u in defender_ship_units + defender_defense_units)
    if atk_left > 0 and def_left == 0:
        res.winner = "attacker"
    elif def_left > 0 and atk_left == 0:
        res.winner = "defender"
    else:
        res.winner = "draw"

    # Debris: 30% of destroyed ship cost (metal + crystal), defenses don't leave debris
    for n, killed in atk_destroyed.items():
        # attacker ship destroyed -> debris
        try:
            stype = ShipType(n)
            m, c, _d, *_ = SHIP_STATS[stype]
            res.debris_metal += int(0.3 * m * killed)
            res.debris_crystal += int(0.3 * c * killed)
        except ValueError:
            pass
    for n, killed in def_destroyed.items():
        try:
            stype = ShipType(n)
            m, c, _d, *_ = SHIP_STATS[stype]
            res.debris_metal += int(0.3 * m * killed)
            res.debris_crystal += int(0.3 * c * killed)
        except ValueError:
            pass  # defense, no debris

    return res
