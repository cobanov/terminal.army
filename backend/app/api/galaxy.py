from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from backend.app.deps import CurrentUser, DBSession
from backend.app.models.planet import Planet
from backend.app.models.user import User
from backend.app.schemas.galaxy import GalaxyResponse, GalaxySlot

router = APIRouter(tags=["galaxy"])


@router.get("/galaxy", response_model=GalaxyResponse)
async def view_galaxy(
    universe_id: int,
    galaxy: int,
    system: int,
    user: CurrentUser,
    db: DBSession,
) -> GalaxyResponse:
    result = await db.execute(
        select(Planet, User.username)
        .join(User, User.id == Planet.owner_user_id)
        .where(
            Planet.universe_id == universe_id,
            Planet.galaxy == galaxy,
            Planet.system == system,
        )
    )
    rows = result.all()
    by_position: dict[int, tuple[Planet, str]] = {}
    for planet, username in rows:
        by_position[planet.position] = (planet, username)

    slots: list[GalaxySlot] = []
    for pos in range(1, 16):
        entry = by_position.get(pos)
        if entry is None:
            slots.append(
                GalaxySlot(position=pos, planet_id=None, planet_name=None, owner_username=None)
            )
        else:
            planet, username = entry
            slots.append(
                GalaxySlot(
                    position=pos,
                    planet_id=planet.id,
                    planet_name=planet.name,
                    owner_username=username,
                )
            )

    return GalaxyResponse(
        universe_id=universe_id, galaxy=galaxy, system=system, slots=slots
    )
