"""OGame oyun sabitleri ve tablolari.

Tum degerler OGame Fandom Wiki'den alinmistir:
https://ogame.fandom.com/wiki/Formulas
"""

from __future__ import annotations

from enum import StrEnum


class BuildingType(StrEnum):
    METAL_MINE = "metal_mine"
    CRYSTAL_MINE = "crystal_mine"
    DEUTERIUM_SYNTHESIZER = "deuterium_synthesizer"
    SOLAR_PLANT = "solar_plant"
    FUSION_REACTOR = "fusion_reactor"
    SOLAR_SATELLITE = "solar_satellite"
    ROBOTICS_FACTORY = "robotics_factory"
    SHIPYARD = "shipyard"
    RESEARCH_LAB = "research_lab"
    METAL_STORAGE = "metal_storage"
    CRYSTAL_STORAGE = "crystal_storage"
    DEUTERIUM_TANK = "deuterium_tank"
    NANITE_FACTORY = "nanite_factory"
    MISSILE_SILO = "missile_silo"
    ALLIANCE_DEPOT = "alliance_depot"
    TERRAFORMER = "terraformer"


BUILDING_LABELS: dict[BuildingType, str] = {
    BuildingType.METAL_MINE: "Metal Mine",
    BuildingType.CRYSTAL_MINE: "Crystal Mine",
    BuildingType.DEUTERIUM_SYNTHESIZER: "Deuterium Synthesizer",
    BuildingType.SOLAR_PLANT: "Solar Plant",
    BuildingType.FUSION_REACTOR: "Fusion Reactor",
    BuildingType.SOLAR_SATELLITE: "Solar Satellite",
    BuildingType.ROBOTICS_FACTORY: "Robotics Factory",
    BuildingType.SHIPYARD: "Shipyard",
    BuildingType.RESEARCH_LAB: "Research Laboratory",
    BuildingType.METAL_STORAGE: "Metal Storage",
    BuildingType.CRYSTAL_STORAGE: "Crystal Storage",
    BuildingType.DEUTERIUM_TANK: "Deuterium Tank",
    BuildingType.NANITE_FACTORY: "Nanite Factory",
    BuildingType.MISSILE_SILO: "Missile Silo",
    BuildingType.ALLIANCE_DEPOT: "Alliance Depot",
    BuildingType.TERRAFORMER: "Terraformer",
}


class TechType(StrEnum):
    ENERGY = "energy"
    LASER = "laser"
    ION = "ion"
    HYPERSPACE = "hyperspace"
    PLASMA = "plasma"
    COMPUTER = "computer"
    ASTROPHYSICS = "astrophysics"
    ESPIONAGE = "espionage"
    # Drive technologies
    COMBUSTION_DRIVE = "combustion_drive"
    IMPULSE_DRIVE = "impulse_drive"
    HYPERSPACE_DRIVE = "hyperspace_drive"
    # Combat technologies
    WEAPONS = "weapons"
    SHIELDING = "shielding"
    ARMOUR = "armour"


TECH_LABELS: dict[TechType, str] = {
    TechType.ENERGY: "Energy Technology",
    TechType.LASER: "Laser Technology",
    TechType.ION: "Ion Technology",
    TechType.HYPERSPACE: "Hyperspace Technology",
    TechType.PLASMA: "Plasma Technology",
    TechType.COMPUTER: "Computer Technology",
    TechType.ASTROPHYSICS: "Astrophysics",
    TechType.ESPIONAGE: "Espionage Technology",
    TechType.COMBUSTION_DRIVE: "Combustion Drive",
    TechType.IMPULSE_DRIVE: "Impulse Drive",
    TechType.HYPERSPACE_DRIVE: "Hyperspace Drive",
    TechType.WEAPONS: "Weapons Technology",
    TechType.SHIELDING: "Shielding Technology",
    TechType.ARMOUR: "Armour Technology",
}


class ShipType(StrEnum):
    """Source: https://ogame.fandom.com/wiki/Ships"""
    SMALL_CARGO = "small_cargo"
    LARGE_CARGO = "large_cargo"
    LIGHT_FIGHTER = "light_fighter"
    HEAVY_FIGHTER = "heavy_fighter"
    CRUISER = "cruiser"
    BATTLESHIP = "battleship"
    COLONY_SHIP = "colony_ship"
    RECYCLER = "recycler"
    ESPIONAGE_PROBE = "espionage_probe"
    BOMBER = "bomber"
    DESTROYER = "destroyer"
    BATTLECRUISER = "battlecruiser"


SHIP_LABELS: dict[ShipType, str] = {
    ShipType.SMALL_CARGO: "Small Cargo",
    ShipType.LARGE_CARGO: "Large Cargo",
    ShipType.LIGHT_FIGHTER: "Light Fighter",
    ShipType.HEAVY_FIGHTER: "Heavy Fighter",
    ShipType.CRUISER: "Cruiser",
    ShipType.BATTLESHIP: "Battleship",
    ShipType.COLONY_SHIP: "Colony Ship",
    ShipType.RECYCLER: "Recycler",
    ShipType.ESPIONAGE_PROBE: "Espionage Probe",
    ShipType.BOMBER: "Bomber",
    ShipType.DESTROYER: "Destroyer",
    ShipType.BATTLECRUISER: "Battlecruiser",
}


class DefenseType(StrEnum):
    """Source: https://ogame.fandom.com/wiki/Defense"""
    ROCKET_LAUNCHER = "rocket_launcher"
    LIGHT_LASER = "light_laser"
    HEAVY_LASER = "heavy_laser"
    GAUSS_CANNON = "gauss_cannon"
    ION_CANNON = "ion_cannon"
    PLASMA_TURRET = "plasma_turret"
    SMALL_SHIELD_DOME = "small_shield_dome"
    LARGE_SHIELD_DOME = "large_shield_dome"


DEFENSE_LABELS: dict[DefenseType, str] = {
    DefenseType.ROCKET_LAUNCHER: "Rocket Launcher",
    DefenseType.LIGHT_LASER: "Light Laser",
    DefenseType.HEAVY_LASER: "Heavy Laser",
    DefenseType.GAUSS_CANNON: "Gauss Cannon",
    DefenseType.ION_CANNON: "Ion Cannon",
    DefenseType.PLASMA_TURRET: "Plasma Turret",
    DefenseType.SMALL_SHIELD_DOME: "Small Shield Dome",
    DefenseType.LARGE_SHIELD_DOME: "Large Shield Dome",
}


# Source: https://ogame.fandom.com/wiki/Temperature
# Pozisyon -> (T_max_min, T_max_max). T_min = T_max - 40.
TEMPERATURE_RANGES_BY_POSITION: dict[int, tuple[int, int]] = {
    1: (220, 260),
    2: (170, 210),
    3: (120, 160),
    4: (70, 110),
    5: (60, 100),
    6: (50, 90),
    7: (40, 80),
    8: (30, 70),
    9: (20, 60),
    10: (10, 50),
    11: (0, 40),
    12: (-10, 30),
    13: (-50, -10),
    14: (-90, -50),
    15: (-130, -90),
}

# Source: https://ogame.fandom.com/wiki/Colonizing_in_Redesigned_Universes
FIELDS_RANGES_BY_POSITION: dict[int, tuple[int, int]] = {
    1: (40, 80),
    2: (45, 90),
    3: (50, 100),
    4: (90, 175),
    5: (120, 230),
    6: (140, 260),
    7: (140, 260),
    8: (140, 260),
    9: (140, 260),
    10: (100, 200),
    11: (100, 200),
    12: (100, 200),
    13: (50, 110),
    14: (50, 110),
    15: (50, 110),
}

# Source: https://ogame.fandom.com/wiki/Metal_Mine (position bonus)
METAL_BONUS_BY_POSITION: dict[int, float] = {
    6: 0.17,
    7: 0.23,
    8: 0.35,
    9: 0.23,
    10: 0.17,
}

CRYSTAL_BONUS_BY_POSITION: dict[int, float] = {
    1: 0.40,
    2: 0.30,
    3: 0.20,
}

# Baslangic kaynaklari (yeni gezegen)
STARTING_METAL = 500
STARTING_CRYSTAL = 500
STARTING_DEUTERIUM = 0

# Baslangic alani kullanimi (default 0; binalar build edildikce artar)
STARTING_FIELDS_USED = 0


# Source: https://ogame.fandom.com/wiki/Buildings (cost table)
# (base_metal, base_crystal, base_deut, cost_factor)
BUILDING_COSTS: dict[BuildingType, tuple[int, int, int, float]] = {
    BuildingType.METAL_MINE: (60, 15, 0, 1.5),
    BuildingType.CRYSTAL_MINE: (48, 24, 0, 1.6),
    BuildingType.DEUTERIUM_SYNTHESIZER: (225, 75, 0, 1.5),
    BuildingType.SOLAR_PLANT: (75, 30, 0, 1.5),
    BuildingType.FUSION_REACTOR: (900, 360, 180, 1.8),
    BuildingType.SOLAR_SATELLITE: (0, 2000, 500, 1.0),  # sabit cost per unit
    BuildingType.ROBOTICS_FACTORY: (400, 120, 200, 2.0),
    BuildingType.SHIPYARD: (400, 200, 100, 2.0),
    BuildingType.RESEARCH_LAB: (200, 400, 200, 2.0),
    BuildingType.METAL_STORAGE: (1000, 0, 0, 2.0),
    BuildingType.CRYSTAL_STORAGE: (1000, 500, 0, 2.0),
    BuildingType.DEUTERIUM_TANK: (1000, 1000, 0, 2.0),
    BuildingType.NANITE_FACTORY: (1_000_000, 500_000, 100_000, 2.0),
    BuildingType.MISSILE_SILO: (20_000, 20_000, 1_000, 2.0),
    BuildingType.ALLIANCE_DEPOT: (20_000, 40_000, 0, 2.0),
    BuildingType.TERRAFORMER: (0, 50_000, 100_000, 2.0),
}


# Mine enerji tuketim katsayilari
MINE_ENERGY_COEFF: dict[BuildingType, int] = {
    BuildingType.METAL_MINE: 10,
    BuildingType.CRYSTAL_MINE: 10,
    BuildingType.DEUTERIUM_SYNTHESIZER: 20,
}


# Source: https://ogame.fandom.com/wiki/Research (cost table)
# (base_metal, base_crystal, base_deut, cost_factor)
RESEARCH_COSTS: dict[TechType, tuple[int, int, int, float]] = {
    TechType.ENERGY: (0, 800, 400, 2.0),
    TechType.LASER: (200, 100, 0, 2.0),
    TechType.ION: (1000, 300, 100, 2.0),
    TechType.HYPERSPACE: (0, 4000, 2000, 2.0),
    TechType.PLASMA: (2000, 4000, 1000, 2.0),
    TechType.COMPUTER: (0, 400, 600, 2.0),
    TechType.ASTROPHYSICS: (4000, 8000, 4000, 1.75),
    TechType.ESPIONAGE: (200, 1000, 200, 2.0),
    TechType.COMBUSTION_DRIVE: (400, 0, 600, 2.0),
    TechType.IMPULSE_DRIVE: (2000, 4000, 600, 2.0),
    TechType.HYPERSPACE_DRIVE: (10000, 20000, 6000, 2.0),
    TechType.WEAPONS: (800, 200, 0, 2.0),
    TechType.SHIELDING: (200, 600, 0, 2.0),
    TechType.ARMOUR: (1000, 0, 0, 2.0),
}


# Tech tree prerekizitleri: bir teknoloji icin -> {tech_type: min_level, ...} ve "lab" key'i.
# "lab" research lab seviyesini gosterir; tum gezegenlerin max'i kullanilir.
TECH_PREREQUISITES: dict[TechType, dict[str, int]] = {
    TechType.ENERGY: {"lab": 1},
    TechType.LASER: {"lab": 1, TechType.ENERGY.value: 2},
    TechType.ION: {"lab": 4, TechType.ENERGY.value: 4, TechType.LASER.value: 5},
    TechType.HYPERSPACE: {"lab": 7, TechType.ENERGY.value: 5},
    TechType.PLASMA: {
        "lab": 4,
        TechType.ENERGY.value: 8,
        TechType.LASER.value: 10,
        TechType.ION.value: 5,
    },
    TechType.COMPUTER: {"lab": 1},
    TechType.ASTROPHYSICS: {
        "lab": 3,
        TechType.ESPIONAGE.value: 4,
        # Impulse drive prereq omitted (post-MVP).
    },
    TechType.ESPIONAGE: {"lab": 3},
    TechType.COMBUSTION_DRIVE: {"lab": 1, TechType.ENERGY.value: 1},
    TechType.IMPULSE_DRIVE: {"lab": 2, TechType.ENERGY.value: 1},
    TechType.HYPERSPACE_DRIVE: {"lab": 7, TechType.HYPERSPACE.value: 3},
    TechType.WEAPONS: {"lab": 4},
    TechType.SHIELDING: {"lab": 6, TechType.ENERGY.value: 3},
    TechType.ARMOUR: {"lab": 2},
}


# ---------- Ship stats (Source: https://ogame.fandom.com/wiki/Ships) -------
# (cost_metal, cost_crystal, cost_deut, structural_integrity, shield, weapon, base_speed, cargo_capacity, fuel_consumption)
# Speed = base + driveTech_bonus (combustion +10%/level for basic ships, impulse for mid, hyperspace for large)
# Speed values are baseline at drive tech 0.
SHIP_STATS: dict[ShipType, tuple[int, int, int, int, int, int, int, int, int]] = {
    # name:                (M,    C,     D,   armor, shld, atk,   speed,  cargo, fuel)
    ShipType.SMALL_CARGO:    (2000, 2000, 0,   4000,  10,   5,     5000,   5000,  10),
    ShipType.LARGE_CARGO:    (6000, 6000, 0,   12000, 25,   5,     7500,   25000, 50),
    ShipType.LIGHT_FIGHTER:  (3000, 1000, 0,   4000,  10,   50,    12500,  50,    20),
    ShipType.HEAVY_FIGHTER:  (6000, 4000, 0,   10000, 25,   150,   10000,  100,   75),
    ShipType.CRUISER:        (20000, 7000, 2000, 27000, 50,  400,   15000,  800,   300),
    ShipType.BATTLESHIP:     (45000, 15000, 0,  60000, 200,  1000,  10000,  1500,  500),
    ShipType.COLONY_SHIP:    (10000, 20000, 10000, 30000, 100, 50,  2500,   7500,  1000),
    ShipType.RECYCLER:       (10000, 6000, 2000, 16000, 10,  1,     2000,   20000, 300),
    ShipType.ESPIONAGE_PROBE: (0,    1000, 0,   1000,  1,    1,     100_000_000, 5, 1),
    ShipType.BOMBER:         (50000, 25000, 15000, 75000, 500, 1000, 4000,  500,   1000),
    ShipType.DESTROYER:      (60000, 50000, 15000, 110000, 500, 2000, 5000, 2000,  1000),
    ShipType.BATTLECRUISER:  (30000, 40000, 15000, 70000, 400, 700,  10000, 750,   250),
}


# Ship build prereqs: {ship: {building/tech: min_level}}
# Building prereqs use "shipyard": N; research keys use TechType values.
SHIP_PREREQUISITES: dict[ShipType, dict[str, int]] = {
    ShipType.SMALL_CARGO:     {"shipyard": 2, TechType.COMBUSTION_DRIVE.value: 2},
    ShipType.LARGE_CARGO:     {"shipyard": 4, TechType.COMBUSTION_DRIVE.value: 6},
    ShipType.LIGHT_FIGHTER:   {"shipyard": 1, TechType.COMBUSTION_DRIVE.value: 1},
    ShipType.HEAVY_FIGHTER:   {"shipyard": 3, TechType.ARMOUR.value: 2, TechType.IMPULSE_DRIVE.value: 2},
    ShipType.CRUISER:         {"shipyard": 5, TechType.IMPULSE_DRIVE.value: 4, TechType.ION.value: 2},
    ShipType.BATTLESHIP:      {"shipyard": 7, TechType.HYPERSPACE_DRIVE.value: 4},
    ShipType.COLONY_SHIP:     {"shipyard": 4, TechType.IMPULSE_DRIVE.value: 3},
    ShipType.RECYCLER:        {"shipyard": 4, TechType.COMBUSTION_DRIVE.value: 6, TechType.SHIELDING.value: 2},
    ShipType.ESPIONAGE_PROBE: {"shipyard": 3, TechType.COMBUSTION_DRIVE.value: 3, TechType.ESPIONAGE.value: 2},
    ShipType.BOMBER:          {"shipyard": 8, TechType.IMPULSE_DRIVE.value: 6, TechType.PLASMA.value: 5},
    ShipType.DESTROYER:       {"shipyard": 9, TechType.HYPERSPACE_DRIVE.value: 6, TechType.HYPERSPACE.value: 5},
    ShipType.BATTLECRUISER:   {"shipyard": 8, TechType.HYPERSPACE_DRIVE.value: 5, TechType.LASER.value: 12, TechType.HYPERSPACE.value: 5},
}


# Drive used by each ship for speed-tech bonus
SHIP_DRIVE: dict[ShipType, TechType] = {
    ShipType.SMALL_CARGO: TechType.COMBUSTION_DRIVE,
    ShipType.LARGE_CARGO: TechType.COMBUSTION_DRIVE,
    ShipType.LIGHT_FIGHTER: TechType.COMBUSTION_DRIVE,
    ShipType.RECYCLER: TechType.COMBUSTION_DRIVE,
    ShipType.ESPIONAGE_PROBE: TechType.COMBUSTION_DRIVE,
    ShipType.HEAVY_FIGHTER: TechType.IMPULSE_DRIVE,
    ShipType.CRUISER: TechType.IMPULSE_DRIVE,
    ShipType.COLONY_SHIP: TechType.IMPULSE_DRIVE,
    ShipType.BOMBER: TechType.IMPULSE_DRIVE,
    ShipType.BATTLESHIP: TechType.HYPERSPACE_DRIVE,
    ShipType.DESTROYER: TechType.HYPERSPACE_DRIVE,
    ShipType.BATTLECRUISER: TechType.HYPERSPACE_DRIVE,
}


# ---------- Defense stats -------------------------------------------------
# (cost_metal, cost_crystal, cost_deut, structural_integrity, shield, weapon)
DEFENSE_STATS: dict[DefenseType, tuple[int, int, int, int, int, int]] = {
    DefenseType.ROCKET_LAUNCHER:    (2000, 0, 0,      2000,   20,   80),
    DefenseType.LIGHT_LASER:        (1500, 500, 0,    2000,   25,   100),
    DefenseType.HEAVY_LASER:        (6000, 2000, 0,   8000,   100,  250),
    DefenseType.GAUSS_CANNON:       (20000, 15000, 2000, 35000, 200, 1100),
    DefenseType.ION_CANNON:         (5000, 3000, 0,   8000,   500,  150),
    DefenseType.PLASMA_TURRET:      (50000, 50000, 30000, 100000, 300, 3000),
    DefenseType.SMALL_SHIELD_DOME:  (10000, 10000, 0, 20000,  2000, 1),
    DefenseType.LARGE_SHIELD_DOME:  (50000, 50000, 0, 100000, 10000, 1),
}

DEFENSE_PREREQUISITES: dict[DefenseType, dict[str, int]] = {
    DefenseType.ROCKET_LAUNCHER:   {"shipyard": 1},
    DefenseType.LIGHT_LASER:       {"shipyard": 2, TechType.ENERGY.value: 1, TechType.LASER.value: 3},
    DefenseType.HEAVY_LASER:       {"shipyard": 4, TechType.ENERGY.value: 3, TechType.LASER.value: 6},
    DefenseType.GAUSS_CANNON:      {"shipyard": 6, TechType.WEAPONS.value: 3, TechType.SHIELDING.value: 1, TechType.ENERGY.value: 6},
    DefenseType.ION_CANNON:        {"shipyard": 4, TechType.ION.value: 4},
    DefenseType.PLASMA_TURRET:     {"shipyard": 8, TechType.PLASMA.value: 7},
    DefenseType.SMALL_SHIELD_DOME: {"shipyard": 1, TechType.SHIELDING.value: 2},
    DefenseType.LARGE_SHIELD_DOME: {"shipyard": 6, TechType.SHIELDING.value: 6},
}


# Solar satellite per-unit ureti max'i (CLAUDE.md)
SOLAR_SATELLITE_MAX_OUTPUT = 65
