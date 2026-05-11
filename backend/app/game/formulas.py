"""Saf oyun formulleri.

Tum formuller OGame Fandom Wiki'den derlenmistir.
Bu modul DB ve framework bagimsizdir: input -> output, side effect yok.
"""

from __future__ import annotations

from math import floor

from backend.app.game.constants import (
    BUILDING_COSTS,
    MINE_ENERGY_COEFF,
    RESEARCH_COSTS,
    SOLAR_SATELLITE_MAX_OUTPUT,
    BuildingType,
    TechType,
)


# -------- Maden uretimi (per hour) ----------------------------------------
# Source: https://ogame.fandom.com/wiki/Metal_Mine
def metal_mine_production(
    level: int,
    speed: float = 1.0,
    plasma_tech: int = 0,
    position_bonus: float = 0.0,
) -> float:
    if level <= 0:
        return 0.0
    return 30 * level * (1.1**level) * speed * (1 + plasma_tech * 0.01) * (1 + position_bonus)


# Source: https://ogame.fandom.com/wiki/Crystal_Mine
def crystal_mine_production(
    level: int,
    speed: float = 1.0,
    plasma_tech: int = 0,
    position_bonus: float = 0.0,
) -> float:
    if level <= 0:
        return 0.0
    return 20 * level * (1.1**level) * speed * (1 + plasma_tech * 0.0066) * (1 + position_bonus)


# Source: https://ogame.fandom.com/wiki/Deuterium_Synthesizer
def deuterium_synthesizer_production(
    level: int,
    temp_max: int,
    speed: float = 1.0,
    plasma_tech: int = 0,
) -> float:
    if level <= 0:
        return 0.0
    return (
        10 * level * (1.1**level) * (1.28 - 0.002 * temp_max) * speed * (1 + plasma_tech * 0.0033)
    )


def base_passive_production(speed: float = 1.0) -> tuple[float, float, float]:
    """Level 0 madenler dahi base uretir."""
    return 30.0 * speed, 15.0 * speed, 0.0


# -------- Enerji ------------------------------------------------------------
# Source: https://ogame.fandom.com/wiki/Solar_Plant
def solar_plant_output(level: int) -> int:
    if level <= 0:
        return 0
    return floor(20 * level * (1.1**level))


# Source: https://ogame.fandom.com/wiki/Solar_Satellite
def solar_satellite_output(count: int, avg_temp: int) -> int:
    if count <= 0:
        return 0
    per_unit = min(SOLAR_SATELLITE_MAX_OUTPUT, floor((avg_temp + 160) / 6))
    if per_unit < 0:
        per_unit = 0
    return per_unit * count


# Source: https://ogame.fandom.com/wiki/Fusion_Reactor
def fusion_reactor_output(level: int, energy_tech: int = 0) -> int:
    if level <= 0:
        return 0
    return floor(30 * level * ((1.05 + energy_tech * 0.01) ** level))


def fusion_deut_consumption(level: int) -> int:
    if level <= 0:
        return 0
    return floor(10 * level * (1.1**level))


def mine_energy_consumption(building_type: BuildingType, level: int) -> int:
    """Source: https://ogame.fandom.com/wiki/Metal_Mine
    Energy = floor(coeff * level * 1.1^level)
    coeff = 10 (metal/crystal mine), 20 (deuterium synthesizer)
    """
    if level <= 0:
        return 0
    coeff = MINE_ENERGY_COEFF.get(building_type)
    if coeff is None:
        return 0
    return floor(coeff * level * (1.1**level))


# -------- Insaat / arastirma maliyeti --------------------------------------
def building_cost(building_type: BuildingType, target_level: int) -> tuple[int, int, int]:
    """cost(L+1) = base_cost * factor^L. Burada target_level = L+1."""
    if target_level <= 0:
        return 0, 0, 0
    base_m, base_c, base_d, factor = BUILDING_COSTS[building_type]
    exp = target_level - 1
    return (
        floor(base_m * factor**exp),
        floor(base_c * factor**exp),
        floor(base_d * factor**exp),
    )


def research_cost(tech_type: TechType, target_level: int) -> tuple[int, int, int]:
    if target_level <= 0:
        return 0, 0, 0
    base_m, base_c, base_d, factor = RESEARCH_COSTS[tech_type]
    exp = target_level - 1
    return (
        floor(base_m * factor**exp),
        floor(base_c * factor**exp),
        floor(base_d * factor**exp),
    )


# -------- Insaat / arastirma suresi ----------------------------------------
def build_time_seconds(
    metal: int,
    crystal: int,
    robotics_level: int = 0,
    nanite_level: int = 0,
    speed: float = 1.0,
) -> int:
    """Source: https://ogame.fandom.com/wiki/Formulas"""
    hours = (metal + crystal) / (2500 * (1 + robotics_level) * speed * (2**nanite_level))
    return max(1, int(hours * 3600))


def research_time_seconds(
    metal: int,
    crystal: int,
    lab_level: int = 0,
    speed: float = 1.0,
) -> int:
    hours = (metal + crystal) / (1000 * speed * (1 + lab_level))
    return max(1, int(hours * 3600))
