"""messages table

Revision ID: 0002_messages
Revises: 0001_init
Create Date: 2026-05-11
"""

from __future__ import annotations

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_messages"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sender_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_messages_sender_id", "messages", ["sender_id"])
    op.create_index(
        "ix_messages_recipient_created", "messages", ["recipient_id", "created_at"]
    )
    op.create_index("ix_messages_recipient_unread", "messages", ["recipient_id", "read"])


def downgrade() -> None:
    op.drop_table("messages")
