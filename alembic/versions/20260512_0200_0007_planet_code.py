"""planets.code (short typeable id)

Each planet gets a 4-char code (e.g. A3D5) that's shown in the UI
alongside the planet name. The DB id stays the PK; `code` is the user
identifier. Existing rows are backfilled with random unique codes
during the migration.

Revision ID: 0007_planet_code
Revises: 0006_alliance_join_requests
Create Date: 2026-05-12
"""

from __future__ import annotations

import secrets
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_planet_code"
down_revision: str | None = "0006_alliance_join_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Excludes ambiguous glyphs (I/1, L, O/0).
_CODE_ALPHABET = "ACDEFGHJKLMNPQRSTUVWXYZ23456789"


def _new_code(used: set[str]) -> str:
    while True:
        c = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
        if c not in used:
            used.add(c)
            return c


def upgrade() -> None:
    op.add_column("planets", sa.Column("code", sa.String(8), nullable=True))

    conn = op.get_bind()
    used: set[str] = set()
    res = conn.execute(sa.text("SELECT id FROM planets ORDER BY id"))
    for (pid,) in res.fetchall():
        code = _new_code(used)
        conn.execute(
            sa.text("UPDATE planets SET code = :code WHERE id = :id"),
            {"code": code, "id": pid},
        )

    op.alter_column("planets", "code", nullable=False)
    op.create_index("ix_planets_code", "planets", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_planets_code", table_name="planets")
    op.drop_column("planets", "code")
