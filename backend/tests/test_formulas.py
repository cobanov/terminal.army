from __future__ import annotations

from backend.app.game.constants import BuildingType, TechType
from backend.app.game.formulas import (
    base_passive_production,
    building_cost,
    crystal_mine_production,
    deuterium_synthesizer_production,
    fusion_reactor_output,
    metal_mine_production,
    mine_energy_consumption,
    research_cost,
    solar_plant_output,
    solar_satellite_output,
)


def test_metal_mine_level_0_is_zero() -> None:
    assert metal_mine_production(0) == 0.0


def test_metal_mine_level_1() -> None:
    # 30 * 1 * 1.1 = 33
    assert metal_mine_production(1, speed=1.0) == 33.0


def test_metal_mine_position_bonus() -> None:
    base = metal_mine_production(10, speed=1.0, position_bonus=0.0)
    bonused = metal_mine_production(10, speed=1.0, position_bonus=0.35)
    assert bonused > base


def test_crystal_mine_level_1() -> None:
    # 20 * 1 * 1.1 = 22
    assert crystal_mine_production(1, speed=1.0) == 22.0


def test_deuterium_synthesizer_cold_planet() -> None:
    cold = deuterium_synthesizer_production(10, temp_max=-50)
    warm = deuterium_synthesizer_production(10, temp_max=200)
    assert cold > warm


def test_base_passive() -> None:
    m, c, d = base_passive_production(1.0)
    assert m == 30.0
    assert c == 15.0
    assert d == 0.0


def test_solar_plant_growth() -> None:
    assert solar_plant_output(0) == 0
    assert solar_plant_output(1) > 0
    assert solar_plant_output(10) > solar_plant_output(5)


def test_solar_satellite_max_cap() -> None:
    # Cok yuksek sicaklikta dahi 65 cap
    val = solar_satellite_output(10, avg_temp=10000)
    assert val == 65 * 10


def test_fusion_reactor_zero_at_level_0() -> None:
    assert fusion_reactor_output(0) == 0


def test_mine_energy_consumption_growth() -> None:
    a = mine_energy_consumption(BuildingType.METAL_MINE, 5)
    b = mine_energy_consumption(BuildingType.METAL_MINE, 10)
    assert b > a


def test_building_cost_level_1() -> None:
    m, c, d = building_cost(BuildingType.METAL_MINE, 1)
    assert (m, c, d) == (60, 15, 0)


def test_building_cost_level_2_uses_factor() -> None:
    m, c, d = building_cost(BuildingType.METAL_MINE, 2)
    # 60 * 1.5 = 90, 15 * 1.5 = 22 (floor)
    assert m == 90
    assert c == 22


def test_research_cost_level_1() -> None:
    m, c, d = research_cost(TechType.ENERGY, 1)
    assert (m, c, d) == (0, 800, 400)
