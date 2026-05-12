"""Bootstrap helper: create the admin user from the host.

The /signup and /auth/register routes refuse to hand out the
ADMIN_USERNAME value to anyone (anti-squat). The operator therefore
creates their own admin account via this script after the container
is up.

Usage (interactive):
    docker compose exec backend python -m backend.scripts.create_admin

Usage (non-interactive):
    docker compose exec -e ADMIN_EMAIL=you@x.com \
        -e ADMIN_PASSWORD=$(openssl rand -base64 24) \
        backend python -m backend.scripts.create_admin

The script reads ADMIN_USERNAME from the container env (the same value
your settings already use). It refuses to run if that env is unset.
"""

from __future__ import annotations

import asyncio
import getpass
import os
import sys

from sqlalchemy import select

from backend.app.config import get_settings
from backend.app.db import AsyncSessionLocal
from backend.app.models.user import User
from backend.app.security import hash_password
from backend.app.services.universe_service import (
    assign_starting_planet,
    ensure_default_universe,
    ensure_user_researches,
)


async def main() -> int:
    settings = get_settings()
    username = (settings.admin_username or "").strip()
    if not username:
        print("ADMIN_USERNAME is not set in this container's env.", file=sys.stderr)
        return 2

    email = os.environ.get("ADMIN_EMAIL") or input(f"email for {username}: ").strip()
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass(f"password for {username}: ")
    if len(password) < 10:
        print("password must be at least 10 characters", file=sys.stderr)
        return 2

    async with AsyncSessionLocal() as db:
        existing = await db.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none() is not None:
            print(f"user {username!r} already exists, nothing to do")
            return 0

        universe = await ensure_default_universe(db)
        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            current_universe_id=universe.id,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        await ensure_user_researches(db, user.id)
        await db.commit()
        await assign_starting_planet(db, user.id, universe)

    print(f"✓ created admin user: {username}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
