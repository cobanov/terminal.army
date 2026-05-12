"""Short human-typeable planet code generator (e.g. "A3D5").

The DB id stays the primary key. `code` is shown in the UI alongside
the planet name and accepted by /switch as an alternative to the
per-user planet number.
"""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.planet import Planet

# Excludes ambiguous glyphs (I/1, L, O/0). 31 chars * 4 positions = ~923k
# unique codes, plenty for any single shard.
_CODE_ALPHABET = "ACDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LEN = 4


def _random_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))


async def generate_unique_code(db: AsyncSession, max_tries: int = 20) -> str:
    """Return a planet code not currently taken in the DB.

    Caller is responsible for using it in a transaction that will fail
    on UNIQUE violation (race-safe retry happens at the row-insert
    layer, not here).
    """
    for _ in range(max_tries):
        candidate = _random_code()
        res = await db.execute(select(Planet.id).where(Planet.code == candidate))
        if res.scalar_one_or_none() is None:
            return candidate
    # Pathological — shouldn't happen with 923k space. Let UNIQUE
    # constraint surface the dup on insert.
    return _random_code()
