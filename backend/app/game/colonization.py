"""Gezegen yaratim mantigi. Pure functions."""

from __future__ import annotations

import random
from dataclasses import dataclass

from backend.app.game.constants import (
    CRYSTAL_BONUS_BY_POSITION,
    FIELDS_RANGES_BY_POSITION,
    METAL_BONUS_BY_POSITION,
    TEMPERATURE_RANGES_BY_POSITION,
)


@dataclass(frozen=True)
class PlanetAttributes:
    position: int
    temp_min: int
    temp_max: int
    fields_total: int
    metal_position_bonus: float
    crystal_position_bonus: float


def generate_planet_attributes(position: int, rng: random.Random | None = None) -> PlanetAttributes:
    if position < 1 or position > 15:
        raise ValueError(f"invalid position: {position}")
    rng = rng or random.Random()

    temp_lo, temp_hi = TEMPERATURE_RANGES_BY_POSITION[position]
    temp_max = rng.randint(temp_lo, temp_hi)
    temp_min = temp_max - 40

    fields_lo, fields_hi = FIELDS_RANGES_BY_POSITION[position]
    fields_total = rng.randint(fields_lo, fields_hi)

    return PlanetAttributes(
        position=position,
        temp_min=temp_min,
        temp_max=temp_max,
        fields_total=fields_total,
        metal_position_bonus=METAL_BONUS_BY_POSITION.get(position, 0.0),
        crystal_position_bonus=CRYSTAL_BONUS_BY_POSITION.get(position, 0.0),
    )


def avg_temp(temp_min: int, temp_max: int) -> int:
    return (temp_min + temp_max) // 2
