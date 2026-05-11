from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base

if TYPE_CHECKING:
    from backend.app.models.planet import Planet


class Building(Base):
    __tablename__ = "buildings"
    __table_args__ = (
        UniqueConstraint("planet_id", "building_type", name="uq_planet_building_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    planet_id: Mapped[int] = mapped_column(ForeignKey("planets.id"), nullable=False, index=True)
    building_type: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    planet: Mapped["Planet"] = relationship(back_populates="buildings")
