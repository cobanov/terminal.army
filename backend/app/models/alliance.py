from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db import Base

if TYPE_CHECKING:
    pass


class AllianceRole(StrEnum):
    FOUNDER = "founder"
    LEADER = "leader"
    MEMBER = "member"


class Alliance(Base):
    """An alliance — a player guild within a server.

    OGame conventions: short uppercase tag (2-6 chars) shown as [TAG] next to
    member usernames, long descriptive name, optional public description.
    One alliance per user (enforced by UNIQUE on AllianceMember.user_id).
    """

    __tablename__ = "alliances"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tag: Mapped[str] = mapped_column(String(6), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    founder_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    members: Mapped[list[AllianceMember]] = relationship(
        back_populates="alliance", cascade="all, delete-orphan"
    )


class AllianceMember(Base):
    __tablename__ = "alliance_members"
    __table_args__ = (UniqueConstraint("user_id", name="uq_alliance_member_user"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    alliance_id: Mapped[int] = mapped_column(
        ForeignKey("alliances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default=AllianceRole.MEMBER.value, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    alliance: Mapped[Alliance] = relationship(back_populates="members")
