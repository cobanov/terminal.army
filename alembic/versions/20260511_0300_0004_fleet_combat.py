"""ships, defenses, fleets, fleet_ships, reports

Revision ID: 0004_fleet_combat
Revises: 0003_device_sessions
Create Date: 2026-05-11
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_fleet_combat"
down_revision: str | None = "0003_device_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "planet_ships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("planet_id", sa.Integer(), sa.ForeignKey("planets.id"), nullable=False),
        sa.Column("ship_type", sa.String(32), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("planet_id", "ship_type", name="uq_planet_ship_type"),
    )
    op.create_index("ix_planet_ships_planet", "planet_ships", ["planet_id"])

    op.create_table(
        "planet_defenses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("planet_id", sa.Integer(), sa.ForeignKey("planets.id"), nullable=False),
        sa.Column("defense_type", sa.String(32), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("planet_id", "defense_type", name="uq_planet_defense_type"),
    )
    op.create_index("ix_planet_defenses_planet", "planet_defenses", ["planet_id"])

    op.create_table(
        "fleets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("origin_planet_id", sa.Integer(), sa.ForeignKey("planets.id"), nullable=False),
        sa.Column("mission", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="outbound"),
        sa.Column("universe_id", sa.Integer(), sa.ForeignKey("universes.id"), nullable=False),
        sa.Column("target_galaxy", sa.Integer(), nullable=False),
        sa.Column("target_system", sa.Integer(), nullable=False),
        sa.Column("target_position", sa.Integer(), nullable=False),
        sa.Column("target_planet_id", sa.Integer(), sa.ForeignKey("planets.id"), nullable=True),
        sa.Column("speed_percent", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("departure_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arrival_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("return_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cargo_metal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cargo_crystal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cargo_deuterium", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fuel_cost", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("arrival_processed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("return_processed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_fleets_owner", "fleets", ["owner_id"])
    op.create_index("ix_fleets_origin", "fleets", ["origin_planet_id"])
    op.create_index("ix_fleets_status_arrival", "fleets", ["status", "arrival_at"])
    op.create_index("ix_fleets_status_return", "fleets", ["status", "return_at"])

    op.create_table(
        "fleet_ships",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "fleet_id",
            sa.Integer(),
            sa.ForeignKey("fleets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ship_type", sa.String(32), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_fleet_ships_fleet", "fleet_ships", ["fleet_id"])

    op.create_table(
        "reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("report_type", sa.String(16), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("target_galaxy", sa.Integer(), nullable=False),
        sa.Column("target_system", sa.Integer(), nullable=False),
        sa.Column("target_position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reports_owner", "reports", ["owner_id"])


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_table("fleet_ships")
    op.drop_table("fleets")
    op.drop_table("planet_defenses")
    op.drop_table("planet_ships")
