from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


class Universe(Base):
    __tablename__ = "universes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    speed_economy: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    speed_fleet: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    speed_research: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    galaxies_count: Mapped[int] = mapped_column(Integer, default=9, nullable=False)
    systems_count: Mapped[int] = mapped_column(Integer, default=499, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
