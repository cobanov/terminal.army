from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base

if TYPE_CHECKING:
    from backend.app.models.building import Building
    from backend.app.models.user import User


class Planet(Base):
    __tablename__ = "planets"
    __table_args__ = (
        UniqueConstraint("universe_id", "galaxy", "system", "position", name="uq_planet_coord"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    universe_id: Mapped[int] = mapped_column(ForeignKey("universes.id"), nullable=False, index=True)

    galaxy: Mapped[int] = mapped_column(Integer, nullable=False)
    system: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    name: Mapped[str] = mapped_column(String(64), nullable=False, default="Homeworld")

    fields_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fields_total: Mapped[int] = mapped_column(Integer, default=160, nullable=False)
    temp_min: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    temp_max: Mapped[int] = mapped_column(Integer, default=40, nullable=False)

    resources_metal: Mapped[float] = mapped_column(Float, default=500.0, nullable=False)
    resources_crystal: Mapped[float] = mapped_column(Float, default=500.0, nullable=False)
    resources_deuterium: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    resources_last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    owner: Mapped[User] = relationship(back_populates="planets", foreign_keys=[owner_user_id])
    buildings: Mapped[list[Building]] = relationship(
        back_populates="planet", cascade="all, delete-orphan"
    )
