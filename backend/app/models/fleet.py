from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db import Base


class FleetMission(StrEnum):
    TRANSPORT = "transport"
    ATTACK = "attack"
    ESPIONAGE = "espionage"
    DEPLOY = "deploy"
    COLONIZE = "colonize"
    RECYCLE = "recycle"


class FleetStatus(StrEnum):
    OUTBOUND = "outbound"  # heading to target
    RETURNING = "returning"  # heading back
    ARRIVED = "arrived"  # at target (deploy/colonize done; or before action)
    COMPLETED = "completed"  # fully done (returned)
    DESTROYED = "destroyed"  # lost in combat


class Fleet(Base):
    __tablename__ = "fleets"
    __table_args__ = (
        Index("ix_fleets_status_arrival", "status", "arrival_at"),
        Index("ix_fleets_status_return", "status", "return_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    origin_planet_id: Mapped[int] = mapped_column(
        ForeignKey("planets.id"), nullable=False, index=True
    )

    mission: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=FleetStatus.OUTBOUND.value, nullable=False
    )

    # Target coords (may not map to an existing planet, e.g. empty slot)
    universe_id: Mapped[int] = mapped_column(ForeignKey("universes.id"), nullable=False)
    target_galaxy: Mapped[int] = mapped_column(Integer, nullable=False)
    target_system: Mapped[int] = mapped_column(Integer, nullable=False)
    target_position: Mapped[int] = mapped_column(Integer, nullable=False)
    target_planet_id: Mapped[int | None] = mapped_column(ForeignKey("planets.id"), nullable=True)

    speed_percent: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    departure_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arrival_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    return_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cargo_metal: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cargo_crystal: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cargo_deuterium: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fuel_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    arrival_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    return_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class FleetShip(Base):
    __tablename__ = "fleet_ships"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fleet_id: Mapped[int] = mapped_column(
        ForeignKey("fleets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
