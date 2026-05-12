from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


class QueueType(StrEnum):
    BUILDING = "building"
    RESEARCH = "research"
    SHIP = "ship"
    DEFENSE = "defense"


class BuildQueue(Base):
    __tablename__ = "build_queue"
    __table_args__ = (
        Index("ix_queue_planet_finished", "planet_id", "finished_at"),
        Index("ix_queue_cancelled_finished", "cancelled", "finished_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    planet_id: Mapped[int] = mapped_column(ForeignKey("planets.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    queue_type: Mapped[str] = mapped_column(String(16), nullable=False)
    item_key: Mapped[str] = mapped_column(String(32), nullable=False)
    target_level: Mapped[int] = mapped_column(Integer, nullable=False)

    cost_metal: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_crystal: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_deuterium: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    cancelled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
