"""Production aggregator: tum binalari + tech'leri toplar, hourly rate ve enerji dengesi doner."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.game.colonization import avg_temp
from backend.app.game.constants import BuildingType, TechType
from backend.app.game.formulas import (
    base_passive_production,
    crystal_mine_production,
    deuterium_synthesizer_production,
    fusion_deut_consumption,
    fusion_reactor_output,
    metal_mine_production,
    mine_energy_consumption,
    solar_plant_output,
    solar_satellite_output,
)


@dataclass(frozen=True)
class ProductionReport:
    metal_per_hour: float
    crystal_per_hour: float
    deuterium_per_hour: float
    energy_produced: int
    energy_consumed: int
    production_factor: float
    # gross rates (production_factor uygulanmadan, info icin)
    gross_metal: float
    gross_crystal: float
    gross_deuterium: float

    @property
    def energy_balance(self) -> int:
        return self.energy_produced - self.energy_consumed


def compute_planet_production(
    buildings: dict[BuildingType, int],
    researches: dict[TechType, int],
    temp_min: int,
    temp_max: int,
    metal_position_bonus: float,
    crystal_position_bonus: float,
    speed: float = 1.0,
) -> ProductionReport:
    plasma = researches.get(TechType.PLASMA, 0)
    energy_tech = researches.get(TechType.ENERGY, 0)

    metal_lvl = buildings.get(BuildingType.METAL_MINE, 0)
    crystal_lvl = buildings.get(BuildingType.CRYSTAL_MINE, 0)
    deut_lvl = buildings.get(BuildingType.DEUTERIUM_SYNTHESIZER, 0)

    # Gross production (no energy throttling yet)
    base_m, base_c, base_d = base_passive_production(speed)
    gross_metal = base_m + metal_mine_production(
        metal_lvl, speed, plasma, metal_position_bonus
    )
    gross_crystal = base_c + crystal_mine_production(
        crystal_lvl, speed, plasma, crystal_position_bonus
    )
    gross_deuterium = base_d + deuterium_synthesizer_production(deut_lvl, temp_max, speed, plasma)

    # Energy consumption (only mines)
    energy_consumed = (
        mine_energy_consumption(BuildingType.METAL_MINE, metal_lvl)
        + mine_energy_consumption(BuildingType.CRYSTAL_MINE, crystal_lvl)
        + mine_energy_consumption(BuildingType.DEUTERIUM_SYNTHESIZER, deut_lvl)
    )

    # Energy production
    solar_lvl = buildings.get(BuildingType.SOLAR_PLANT, 0)
    fusion_lvl = buildings.get(BuildingType.FUSION_REACTOR, 0)
    sat_count = buildings.get(BuildingType.SOLAR_SATELLITE, 0)

    avg_t = avg_temp(temp_min, temp_max)
    energy_produced = (
        solar_plant_output(solar_lvl)
        + solar_satellite_output(sat_count, avg_t)
        + fusion_reactor_output(fusion_lvl, energy_tech)
    )

    # Fusion deuterium tuketimi (gross_deuterium'dan dusulur)
    fusion_deut = fusion_deut_consumption(fusion_lvl)
    gross_deuterium = max(0.0, gross_deuterium - fusion_deut)

    # Production factor
    if energy_consumed == 0:
        production_factor = 1.0
    else:
        production_factor = min(1.0, energy_produced / energy_consumed)

    # Net rates: mine'lar production_factor ile, base passive scaled etmez
    net_metal_mine = (gross_metal - base_m) * production_factor
    net_crystal_mine = (gross_crystal - base_c) * production_factor
    deut_mine_raw = deuterium_synthesizer_production(deut_lvl, temp_max, speed, plasma)
    net_deut_mine = deut_mine_raw * production_factor

    net_metal = base_m + net_metal_mine
    net_crystal = base_c + net_crystal_mine
    net_deuterium = base_d + net_deut_mine - fusion_deut

    return ProductionReport(
        metal_per_hour=max(0.0, net_metal),
        crystal_per_hour=max(0.0, net_crystal),
        deuterium_per_hour=max(0.0, net_deuterium),
        energy_produced=energy_produced,
        energy_consumed=energy_consumed,
        production_factor=production_factor,
        gross_metal=gross_metal,
        gross_crystal=gross_crystal,
        gross_deuterium=gross_deuterium,
    )
