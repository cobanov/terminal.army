"""init schema

Revision ID: 0001_init
Revises:
Create Date: 2026-05-11
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "universes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("speed_economy", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("speed_fleet", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("speed_research", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("galaxies_count", sa.Integer(), nullable=False, server_default="9"),
        sa.Column("systems_count", sa.Integer(), nullable=False, server_default="499"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("current_universe_id", sa.Integer(), sa.ForeignKey("universes.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "planets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "owner_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "universe_id",
            sa.Integer(),
            sa.ForeignKey("universes.id"),
            nullable=False,
        ),
        sa.Column("galaxy", sa.Integer(), nullable=False),
        sa.Column("system", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(64), nullable=False, server_default="Homeworld"),
        sa.Column("fields_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fields_total", sa.Integer(), nullable=False, server_default="160"),
        sa.Column("temp_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("temp_max", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("resources_metal", sa.Float(), nullable=False, server_default="500"),
        sa.Column("resources_crystal", sa.Float(), nullable=False, server_default="500"),
        sa.Column("resources_deuterium", sa.Float(), nullable=False, server_default="0"),
        sa.Column("resources_last_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "universe_id", "galaxy", "system", "position", name="uq_planet_coord"
        ),
    )
    op.create_index("ix_planets_owner", "planets", ["owner_user_id"])
    op.create_index("ix_planets_universe", "planets", ["universe_id"])

    op.create_table(
        "buildings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("planet_id", sa.Integer(), sa.ForeignKey("planets.id"), nullable=False),
        sa.Column("building_type", sa.String(32), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("planet_id", "building_type", name="uq_planet_building_type"),
    )
    op.create_index("ix_buildings_planet", "buildings", ["planet_id"])

    op.create_table(
        "researches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tech_type", sa.String(32), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "tech_type", name="uq_user_tech"),
    )
    op.create_index("ix_researches_user", "researches", ["user_id"])

    op.create_table(
        "build_queue",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("planet_id", sa.Integer(), sa.ForeignKey("planets.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("queue_type", sa.String(16), nullable=False),
        sa.Column("item_key", sa.String(32), nullable=False),
        sa.Column("target_level", sa.Integer(), nullable=False),
        sa.Column("cost_metal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_crystal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_deuterium", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_queue_user", "build_queue", ["user_id"])
    op.create_index("ix_queue_planet_finished", "build_queue", ["planet_id", "finished_at"])
    op.create_index(
        "ix_queue_cancelled_finished", "build_queue", ["cancelled", "finished_at"]
    )


def downgrade() -> None:
    op.drop_table("build_queue")
    op.drop_table("researches")
    op.drop_table("buildings")
    op.drop_table("planets")
    op.drop_table("users")
    op.drop_table("universes")
