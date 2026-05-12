from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base

if TYPE_CHECKING:
    from backend.app.models.planet import Planet
    from backend.app.models.research import Research
    from backend.app.models.universe import Universe


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    current_universe_id: Mapped[int | None] = mapped_column(
        ForeignKey("universes.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    universe: Mapped[Universe | None] = relationship(foreign_keys=[current_universe_id])
    planets: Mapped[list[Planet]] = relationship(back_populates="owner")
    researches: Mapped[list[Research]] = relationship(back_populates="user")
