from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


class ReportType(StrEnum):
    ESPIONAGE = "espionage"
    COMBAT = "combat"


class Report(Base):
    """Espionage / combat reports stored as JSON-ish text (simple)."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    report_type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)  # JSON or formatted text
    target_galaxy: Mapped[int] = mapped_column(Integer, nullable=False)
    target_system: Mapped[int] = mapped_column(Integer, nullable=False)
    target_position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
