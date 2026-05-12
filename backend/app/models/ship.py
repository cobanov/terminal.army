from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


class PlanetShip(Base):
    """Ships stationed on a planet."""

    __tablename__ = "planet_ships"
    __table_args__ = (UniqueConstraint("planet_id", "ship_type", name="uq_planet_ship_type"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    planet_id: Mapped[int] = mapped_column(ForeignKey("planets.id"), nullable=False, index=True)
    ship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PlanetDefense(Base):
    """Defensive structures on a planet."""

    __tablename__ = "planet_defenses"
    __table_args__ = (UniqueConstraint("planet_id", "defense_type", name="uq_planet_defense_type"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    planet_id: Mapped[int] = mapped_column(ForeignKey("planets.id"), nullable=False, index=True)
    defense_type: Mapped[str] = mapped_column(String(32), nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
