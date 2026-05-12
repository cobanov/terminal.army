"""Leaderboard JSON API.

GET /leaderboard       → top N players ranked by total points
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from backend.app.deps import CurrentUser, DBSession
from backend.app.models.alliance import Alliance, AllianceMember
from backend.app.models.user import User
from backend.app.services.scoring_service import user_points

router = APIRouter(tags=["leaderboard"])


class LeaderboardRow(BaseModel):
    rank: int
    user_id: int
    username: str
    alliance_tag: str | None = None
    building_points: int
    research_points: int
    fleet_points: int
    defense_points: int
    total_points: int


class LeaderboardResponse(BaseModel):
    total_players: int
    rows: list[LeaderboardRow]
    my_rank: int | None = None
    my_total: int | None = None


class MyPoints(BaseModel):
    building_points: int
    research_points: int
    fleet_points: int
    defense_points: int
    total_points: int


@router.get("/me/points", response_model=MyPoints)
async def get_my_points(user: CurrentUser, db: DBSession) -> MyPoints:
    """Cheap per-user score breakdown — used by the TUI topbar."""
    pts = await user_points(db, user.id)
    return MyPoints(**pts)


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(user: CurrentUser, db: DBSession, limit: int = 50) -> LeaderboardResponse:
    users_res = await db.execute(select(User).order_by(User.id))
    users = list(users_res.scalars().all())

    # Pre-load alliance membership for tag display
    member_res = await db.execute(
        select(AllianceMember.user_id, Alliance.tag).join(
            Alliance, Alliance.id == AllianceMember.alliance_id
        )
    )
    alliance_by_user: dict[int, str] = {uid: tag for uid, tag in member_res.all()}

    # Score every user
    scored: list[tuple[User, dict]] = []
    for u in users:
        pts = await user_points(db, u.id)
        scored.append((u, pts))

    scored.sort(key=lambda t: t[1]["total_points"], reverse=True)

    rows: list[LeaderboardRow] = []
    my_rank: int | None = None
    my_total: int | None = None
    for i, (u, pts) in enumerate(scored, start=1):
        if u.id == user.id:
            my_rank = i
            my_total = pts["total_points"]
        if i <= limit:
            rows.append(
                LeaderboardRow(
                    rank=i,
                    user_id=u.id,
                    username=u.username,
                    alliance_tag=alliance_by_user.get(u.id),
                    **pts,
                )
            )

    return LeaderboardResponse(
        total_players=len(scored),
        rows=rows,
        my_rank=my_rank,
        my_total=my_total,
    )
