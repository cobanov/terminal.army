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

import asyncio
import os
import subprocess
import sys

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine


def _async_url() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    if not raw:
        print("DATABASE_URL is unset", file=sys.stderr)
        sys.exit(2)
    return raw


async def _probe() -> tuple[bool, bool]:
    engine = create_async_engine(_async_url())
    try:
        async with engine.connect() as conn:
            def _check(sync_conn: object) -> tuple[bool, bool]:
                insp = inspect(sync_conn)
                return insp.has_table("alembic_version"), insp.has_table("users")

            return await conn.run_sync(_check)
    finally:
        await engine.dispose()


def main() -> int:
    has_alembic, has_app = asyncio.run(_probe())

    if has_alembic:
        print("[migrate] alembic_version found -> upgrade head")
        return subprocess.call(["alembic", "upgrade", "head"])
    if has_app:
        print("[migrate] existing schema without alembic -> stamp head")
        return subprocess.call(["alembic", "stamp", "head"])
    print("[migrate] fresh database -> upgrade head")
    return subprocess.call(["alembic", "upgrade", "head"])


if __name__ == "__main__":
    raise SystemExit(main())
