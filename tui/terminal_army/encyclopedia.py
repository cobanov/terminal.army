"""Static descriptions for /info <thing>.

The numeric data (cost, build time, current count) is on the server and
shown by /buildings, /research, /ships, /defense. This catalog only
holds the human-readable role description.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    key: str
    category: str
    label: str
    description: str
    see: str  # which slash command shows the live cost


# Buildings -----------------------------------------------------------------
_B = "building"
_BUILDINGS: dict[str, Entry] = {
    "metal_mine": Entry(
        "metal_mine",
        _B,
        "Metal Mine",
        "Mines metal from the planet's crust. Production scales exponentially "
        "with level. Foundation of every economy.",
        "/resources",
    ),
    "crystal_mine": Entry(
        "crystal_mine",
        _B,
        "Crystal Mine",
        "Refines crystal — needed for almost every research, ship, and defense. "
        "Production scales like metal but with a steeper cost factor.",
        "/resources",
    ),
    "deuterium_synthesizer": Entry(
        "deuterium_synthesizer",
        _B,
        "Deuterium Synthesizer",
        "Extracts deuterium from seawater. Output drops with planet "
        "temperature — cold positions (13-15) produce more.",
        "/resources",
    ),
    "solar_plant": Entry(
        "solar_plant",
        _B,
        "Solar Plant",
        "Primary energy source. Mines won't run at full speed without enough "
        "energy; check your balance in the topbar.",
        "/resources",
    ),
    "fusion_reactor": Entry(
        "fusion_reactor",
        _B,
        "Fusion Reactor",
        "Secondary energy generator that burns deuterium. Required when solar "
        "+ satellites can't keep up with mine demand.",
        "/resources",
    ),
    "solar_satellite": Entry(
        "solar_satellite",
        _B,
        "Solar Satellite",
        "Cheap orbital energy supplement. Output depends on planet temperature "
        "(hot = better). Vulnerable in combat.",
        "/resources",
    ),
    "crawler": Entry(
        "crawler",
        _B,
        "Crawler",
        "Mining drone. Each crawler adds +0.02% to all mine output, capped at +50%.",
        "/resources",
    ),
    "metal_storage": Entry(
        "metal_storage",
        _B,
        "Metal Storage",
        "Raises the metal cap. Mines stop producing when storage is full — "
        "upgrade if you're losing production to overflow.",
        "/resources",
    ),
    "crystal_storage": Entry(
        "crystal_storage",
        _B,
        "Crystal Storage",
        "Same idea as Metal Storage but for crystal.",
        "/resources",
    ),
    "deuterium_tank": Entry(
        "deuterium_tank",
        _B,
        "Deuterium Tank",
        "Stores deuterium. Especially valuable around colonies you don't visit often.",
        "/resources",
    ),
    "robotics_factory": Entry(
        "robotics_factory",
        _B,
        "Robotics Factory",
        "Speeds up construction of buildings, ships, and defenses. Every level "
        "shaves time off all build queues.",
        "/facilities",
    ),
    "shipyard": Entry(
        "shipyard",
        _B,
        "Shipyard",
        "Unlocks ships and defenses. Each ship/defense has a minimum shipyard level requirement.",
        "/facilities",
    ),
    "research_lab": Entry(
        "research_lab",
        _B,
        "Research Laboratory",
        "Required to research any tech. Research uses the HIGHEST lab level "
        "across all your planets.",
        "/facilities",
    ),
    "alliance_depot": Entry(
        "alliance_depot",
        _B,
        "Alliance Depot",
        "Allows allied fleets to refuel at your planet (post-MVP feature).",
        "/facilities",
    ),
    "missile_silo": Entry(
        "missile_silo",
        _B,
        "Missile Silo",
        "Stores interplanetary and anti-ballistic missiles (post-MVP).",
        "/facilities",
    ),
    "nanite_factory": Entry(
        "nanite_factory",
        _B,
        "Nanite Factory",
        "Multiplicative build-time reduction on top of Robotics. Endgame: "
        "every level halves construction time.",
        "/facilities",
    ),
    "terraformer": Entry(
        "terraformer",
        _B,
        "Terraformer",
        "Adds free fields to a planet (post-MVP).",
        "/facilities",
    ),
}


# Research ------------------------------------------------------------------
_T = "tech"
_TECHS: dict[str, Entry] = {
    "energy": Entry(
        "energy",
        _T,
        "Energy Technology",
        "Gates other tech and improves Fusion Reactor efficiency.",
        "/research",
    ),
    "laser": Entry(
        "laser",
        _T,
        "Laser Technology",
        "Unlocks laser-based defenses and prerequisites Ion.",
        "/research",
    ),
    "ion": Entry(
        "ion",
        _T,
        "Ion Technology",
        "Heavy electronic warfare; unlocks Ion Cannon and Cruiser.",
        "/research",
    ),
    "hyperspace": Entry(
        "hyperspace",
        _T,
        "Hyperspace Technology",
        "Unlocks Hyperspace Drive and several capital ships.",
        "/research",
    ),
    "plasma": Entry(
        "plasma",
        _T,
        "Plasma Technology",
        "Unlocks Plasma Turret and Bomber. Late-game crystal sink.",
        "/research",
    ),
    "computer": Entry(
        "computer",
        _T,
        "Computer Technology",
        "Each level adds one parallel fleet slot.",
        "/research",
    ),
    "astrophysics": Entry(
        "astrophysics",
        _T,
        "Astrophysics",
        "Unlocks colony slots. Odd levels add a new colony slot.",
        "/research",
    ),
    "espionage": Entry(
        "espionage",
        _T,
        "Espionage Technology",
        "Improves espionage report detail and counter-espionage chance.",
        "/research",
    ),
    "combustion_drive": Entry(
        "combustion_drive",
        _T,
        "Combustion Drive",
        "+10% speed per level for early cargos and fighters.",
        "/research",
    ),
    "impulse_drive": Entry(
        "impulse_drive",
        _T,
        "Impulse Drive",
        "+20% speed per level for mid-tier ships (Cruiser, Bomber, Colony Ship).",
        "/research",
    ),
    "hyperspace_drive": Entry(
        "hyperspace_drive",
        _T,
        "Hyperspace Drive",
        "+30% speed per level for capital ships (Battleship, Destroyer).",
        "/research",
    ),
    "weapons": Entry(
        "weapons",
        _T,
        "Weapons Technology",
        "+10% weapon damage for all ships and defenses, per level.",
        "/research",
    ),
    "shielding": Entry(
        "shielding",
        _T,
        "Shielding Technology",
        "+10% shield strength for all ships and defenses, per level.",
        "/research",
    ),
    "armour": Entry(
        "armour",
        _T,
        "Armour Technology",
        "+10% hull strength for all ships and defenses, per level.",
        "/research",
    ),
}


# Ships ---------------------------------------------------------------------
_S = "ship"
_SHIPS: dict[str, Entry] = {
    "small_cargo": Entry(
        "small_cargo",
        _S,
        "Small Cargo",
        "Fast hauler. 5000 cargo capacity. Workhorse of early raids and fleetsaves.",
        "/ships",
    ),
    "large_cargo": Entry(
        "large_cargo",
        _S,
        "Large Cargo",
        "Slow but high-capacity hauler (25k cargo). Standard farming ship.",
        "/ships",
    ),
    "light_fighter": Entry(
        "light_fighter",
        _S,
        "Light Fighter",
        "Cheap interceptor. Effective in mass against light defenses.",
        "/ships",
    ),
    "heavy_fighter": Entry(
        "heavy_fighter",
        _S,
        "Heavy Fighter",
        "Mid-tier interceptor with better armour than Light Fighters.",
        "/ships",
    ),
    "cruiser": Entry(
        "cruiser",
        _S,
        "Cruiser",
        "Anti-fighter capital. Rapid-fire vs Light Fighter and Rocket Launcher.",
        "/ships",
    ),
    "battleship": Entry(
        "battleship",
        _S,
        "Battleship",
        "Backbone of a fleeter army. Hyperspace drive, high firepower.",
        "/ships",
    ),
    "colony_ship": Entry(
        "colony_ship",
        _S,
        "Colony Ship",
        "One-shot ship that founds a colony on an unoccupied slot.",
        "/ships",
    ),
    "recycler": Entry(
        "recycler",
        _S,
        "Recycler",
        "Collects debris from combat sites. The only way to recover scrap.",
        "/ships",
    ),
    "espionage_probe": Entry(
        "espionage_probe",
        _S,
        "Espionage Probe",
        "Tiny scouting drone. Sends back an Espionage Report when it arrives.",
        "/ships",
    ),
    "bomber": Entry(
        "bomber",
        _S,
        "Bomber",
        "Anti-defense specialist with rapid-fire vs Plasma Turret, Gauss, Ion.",
        "/ships",
    ),
    "destroyer": Entry(
        "destroyer",
        _S,
        "Destroyer",
        "Anti-Battlecruiser capital. High firepower, expensive.",
        "/ships",
    ),
    "battlecruiser": Entry(
        "battlecruiser",
        _S,
        "Battlecruiser",
        "Fast multipurpose capital with rapid-fire vs many ship classes.",
        "/ships",
    ),
}


# Defenses ------------------------------------------------------------------
_D = "defense"
_DEFENSES: dict[str, Entry] = {
    "rocket_launcher": Entry(
        "rocket_launcher",
        _D,
        "Rocket Launcher",
        "Cheap surface battery. Easily massed; weak per unit. 70% rebuild chance after combat.",
        "/defense",
    ),
    "light_laser": Entry(
        "light_laser",
        _D,
        "Light Laser",
        "Slightly stronger than Rocket Launcher. Cheap mass deterrent.",
        "/defense",
    ),
    "heavy_laser": Entry(
        "heavy_laser",
        _D,
        "Heavy Laser",
        "Mid-tier turret. Decent shield + hull. Effective vs Heavy Fighter.",
        "/defense",
    ),
    "gauss_cannon": Entry(
        "gauss_cannon",
        _D,
        "Gauss Cannon",
        "Heavy kinetic cannon. High weapon power, expensive.",
        "/defense",
    ),
    "ion_cannon": Entry(
        "ion_cannon",
        _D,
        "Ion Cannon",
        "Disruptor turret with massive shield (500). Tanks like a brick.",
        "/defense",
    ),
    "plasma_turret": Entry(
        "plasma_turret",
        _D,
        "Plasma Turret",
        "Top-tier surface battery. 3000 weapon power, 100k hull. Costly.",
        "/defense",
    ),
    "small_shield_dome": Entry(
        "small_shield_dome",
        _D,
        "Small Shield Dome",
        "Unique per planet (max 1). 2000 shield buffer over the planet.",
        "/defense",
    ),
    "large_shield_dome": Entry(
        "large_shield_dome",
        _D,
        "Large Shield Dome",
        "Unique per planet (max 1). 10k shield. Stacks with Small.",
        "/defense",
    ),
}


# Index ---------------------------------------------------------------------
ALL: dict[str, Entry] = {**_BUILDINGS, **_TECHS, **_SHIPS, **_DEFENSES}


def lookup(arg: str) -> Entry | None:
    """Case-insensitive exact-or-prefix lookup. Returns None on ambiguity."""
    key = arg.lower().strip().replace(" ", "_").replace("-", "_")
    if key in ALL:
        return ALL[key]
    # Prefix match — only accept if unique.
    matches = [v for k, v in ALL.items() if k.startswith(key)]
    if len(matches) == 1:
        return matches[0]
    return None


def suggestions(prefix: str, limit: int = 12) -> list[str]:
    """Keys starting with the given prefix (lowercase)."""
    p = prefix.lower().strip()
    return [k for k in ALL if k.startswith(p)][:limit]
