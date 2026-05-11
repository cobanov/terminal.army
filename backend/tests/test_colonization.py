from __future__ import annotations

import random

from backend.app.game.colonization import generate_planet_attributes
from backend.app.game.constants import (
    FIELDS_RANGES_BY_POSITION,
    TEMPERATURE_RANGES_BY_POSITION,
)


def test_planet_attributes_within_ranges() -> None:
    rng = random.Random(42)
    for pos in range(1, 16):
        for _ in range(50):
            attrs = generate_planet_attributes(pos, rng)
            tlo, thi = TEMPERATURE_RANGES_BY_POSITION[pos]
            flo, fhi = FIELDS_RANGES_BY_POSITION[pos]
            assert tlo <= attrs.temp_max <= thi
            assert attrs.temp_min == attrs.temp_max - 40
            assert flo <= attrs.fields_total <= fhi


def test_position_bonus_position_8_metal() -> None:
    attrs = generate_planet_attributes(8, random.Random(0))
    assert attrs.metal_position_bonus == 0.35
    assert attrs.crystal_position_bonus == 0.0


def test_position_bonus_position_1_crystal() -> None:
    attrs = generate_planet_attributes(1, random.Random(0))
    assert attrs.metal_position_bonus == 0.0
    assert attrs.crystal_position_bonus == 0.40
