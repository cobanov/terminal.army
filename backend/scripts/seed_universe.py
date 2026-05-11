"""Seed default universe. Idempotent."""

from __future__ import annotations

import asyncio

from backend.app.config import get_settings
from backend.app.db import AsyncSessionLocal, init_db
from backend.app.services.universe_service import ensure_default_universe


async def main() -> None:
    settings = get_settings()
    await init_db()
    async with AsyncSessionLocal() as db:
        universe = await ensure_default_universe(
            db, name=settings.default_universe_name, speed=settings.default_universe_speed
        )
        print(f"Universe ready: id={universe.id}, name={universe.name}")


if __name__ == "__main__":
    asyncio.run(main())
