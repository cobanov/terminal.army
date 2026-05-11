"""Admin endpoints: runtime universe tuning (speed multiplier).

Auth model: the user whose username equals settings.admin_username is the
admin. Everyone else gets 403.

Operator sets ADMIN_USERNAME=<their_username> in the container env to
unlock this.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from backend.app.config import get_settings
from backend.app.deps import CurrentUser, DBSession
from backend.app.services.universe_service import get_default_universe

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(user) -> None:
    settings = get_settings()
    admin = (settings.admin_username or "").strip()
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin endpoints disabled (no ADMIN_USERNAME configured)",
        )
    if user.username != admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="not authorized",
        )


class UniverseStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    speed_economy: int
    speed_fleet: int
    speed_research: int
    galaxies_count: int
    systems_count: int
    is_active: bool


class SpeedRequest(BaseModel):
    speed: int = Field(ge=1, le=100, description="universe speed multiplier 1..100")


@router.get("/universe", response_model=UniverseStatus)
async def get_universe(user: CurrentUser, db: DBSession) -> UniverseStatus:
    _require_admin(user)
    universe = await get_default_universe(db)
    if universe is None:
        raise HTTPException(status_code=404, detail="no universe")
    return UniverseStatus.model_validate(universe)


@router.post("/universe/speed", response_model=UniverseStatus)
async def set_universe_speed(
    body: SpeedRequest, user: CurrentUser, db: DBSession
) -> UniverseStatus:
    """Set economy, fleet, and research speed to the same multiplier.

    Takes effect immediately. Existing planet resources are
    recomputed lazily on the next API touch.
    """
    _require_admin(user)
    universe = await get_default_universe(db)
    if universe is None:
        raise HTTPException(status_code=404, detail="no universe")
    universe.speed_economy = body.speed
    universe.speed_fleet = body.speed
    universe.speed_research = body.speed
    await db.commit()
    await db.refresh(universe)
    return UniverseStatus.model_validate(universe)
