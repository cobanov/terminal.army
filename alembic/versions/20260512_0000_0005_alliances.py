"""alliances + alliance_members tables

Revision ID: 0005_alliances
Revises: 0004_fleet_combat
Create Date: 2026-05-12
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_alliances"
down_revision: str | None = "0004_fleet_combat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alliances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tag", sa.String(6), nullable=False, unique=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("founder_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alliances_tag", "alliances", ["tag"])

    op.create_table(
        "alliance_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "alliance_id", sa.Integer(),
            sa.ForeignKey("alliances.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="member"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_alliance_member_user"),
    )
    op.create_index("ix_alliance_members_alliance", "alliance_members", ["alliance_id"])


def downgrade() -> None:
    op.drop_table("alliance_members")
    op.drop_table("alliances")
