"""Public /stats endpoint for the lobby to poll.

Returns server identity (name, description, max users) plus current
population (registered + recently-active). No auth required so the lobby
can poll multiple servers without holding any tokens.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import and_, func, select

from backend.app.config import get_settings
from backend.app.deps import DBSession
from backend.app.models.user import User

router = APIRouter(tags=["stats"])


class ServerStats(BaseModel):
    name: str
    description: str
    max_users: int
    registered: int
    active_24h: int
    full: bool
    version: str = "0.1.0"


@router.get("/stats", response_model=ServerStats)
async def server_stats(db: DBSession) -> ServerStats:
    settings = get_settings()

    total_res = await db.execute(select(func.count()).select_from(User))
    registered = int(total_res.scalar() or 0)

    # "Active" = touched their account in the last 24 hours
    since = datetime.now(UTC) - timedelta(hours=24)
    active_res = await db.execute(
        select(func.count())
        .select_from(User)
        .where(and_(User.created_at >= since))  # crude: created in last 24h
    )
    active_24h = int(active_res.scalar() or 0)

    return ServerStats(
        name=settings.server_name,
        description=settings.server_description,
        max_users=settings.server_max_users,
        registered=registered,
        active_24h=active_24h,
        full=registered >= settings.server_max_users,
    )
