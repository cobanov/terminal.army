"""alliance_join_requests table

Founder-approved alliance membership: applicants insert a row, founder
approves (member row + delete request) or rejects (delete request).

Revision ID: 0006_alliance_join_requests
Revises: 0005_alliances
Create Date: 2026-05-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_alliance_join_requests"
down_revision: str | None = "0005_alliances"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alliance_join_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "alliance_id",
            sa.Integer(),
            sa.ForeignKey("alliances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "alliance_id", "user_id", name="uq_alliance_join_request_pair"
        ),
    )
    op.create_index(
        "ix_alliance_join_requests_alliance",
        "alliance_join_requests",
        ["alliance_id"],
    )
    op.create_index(
        "ix_alliance_join_requests_user",
        "alliance_join_requests",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_table("alliance_join_requests")
