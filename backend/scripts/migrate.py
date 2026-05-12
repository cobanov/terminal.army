"""Smart startup migrator.

Three cases at container boot:

  1. Fresh database (no `alembic_version`, no app tables yet)
     → run `alembic upgrade head` to create everything from scratch.

  2. Existing database built via SQLAlchemy `create_all` (has app
     tables but no `alembic_version` row)
     → stamp alembic to the head revision so future migrations apply
     incrementally. No DDL is run; the schema is assumed to match head.

  3. Existing database already under alembic control
     → run `alembic upgrade head` to apply any pending migrations.

Called from the container CMD before terminal-army-server boots.
"""

from __future__ import annotations

import os
import subprocess
import sys

from sqlalchemy import create_engine, inspect


def _sync_url() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        print("DATABASE_URL is unset", file=sys.stderr)
        sys.exit(2)
    # Alembic uses sync drivers; flip the +asyncpg suffix to plain
    # postgresql so the sync engine can connect.
    return raw.replace("+asyncpg", "").replace("+aiosqlite", "")


def main() -> int:
    engine = create_engine(_sync_url())
    with engine.connect() as conn:
        has_alembic = inspect(conn).has_table("alembic_version")
        # `users` is a stable canary — present in every revision from
        # the initial migration onward.
        has_app = inspect(conn).has_table("users")

    if has_alembic:
        print("[migrate] alembic_version found → upgrade head")
        return subprocess.call(["alembic", "upgrade", "head"])
    if has_app:
        print("[migrate] existing schema without alembic → stamp head")
        return subprocess.call(["alembic", "stamp", "head"])
    print("[migrate] fresh database → upgrade head")
    return subprocess.call(["alembic", "upgrade", "head"])


if __name__ == "__main__":
    raise SystemExit(main())
