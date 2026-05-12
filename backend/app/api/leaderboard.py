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


class PublicLeaderboardRow(BaseModel):
    rank: int
    username: str
    alliance_tag: str | None = None
    total_points: int


class PublicLeaderboardResponse(BaseModel):
    server_name: str
    total_players: int
    rows: list[PublicLeaderboardRow]


@router.get("/leaderboard/public", response_model=PublicLeaderboardResponse)
async def get_public_leaderboard(
    db: DBSession, limit: int = 20
) -> PublicLeaderboardResponse:
    """Unauthenticated top-N list. Used by the lobby to poll every shard."""
    from backend.app.config import get_settings

    users_res = await db.execute(select(User).order_by(User.id))
    users = list(users_res.scalars().all())

    member_res = await db.execute(
        select(AllianceMember.user_id, Alliance.tag)
        .join(Alliance, Alliance.id == AllianceMember.alliance_id)
    )
    alliance_by_user: dict[int, str] = {uid: tag for uid, tag in member_res.all()}

    scored: list[tuple[User, int]] = []
    for u in users:
        pts = await user_points(db, u.id)
        scored.append((u, pts["total_points"]))
    scored.sort(key=lambda t: t[1], reverse=True)

    rows = [
        PublicLeaderboardRow(
            rank=i,
            username=u.username,
            alliance_tag=alliance_by_user.get(u.id),
            total_points=total,
        )
        for i, (u, total) in enumerate(scored[:limit], start=1)
    ]
    return PublicLeaderboardResponse(
        server_name=get_settings().server_name,
        total_players=len(scored),
        rows=rows,
    )


@router.get("/leaderboard", response_model=LeaderboardResponse)
async def get_leaderboard(
    user: CurrentUser, db: DBSession, limit: int = 50
) -> LeaderboardResponse:
    users_res = await db.execute(select(User).order_by(User.id))
    users = list(users_res.scalars().all())

    # Pre-load alliance membership for tag display
    member_res = await db.execute(
        select(AllianceMember.user_id, Alliance.tag)
        .join(Alliance, Alliance.id == AllianceMember.alliance_id)
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
            rows.append(LeaderboardRow(
                rank=i, user_id=u.id, username=u.username,
                alliance_tag=alliance_by_user.get(u.id),
                **pts,
            ))

    return LeaderboardResponse(
        total_players=len(scored),
        rows=rows,
        my_rank=my_rank,
        my_total=my_total,
    )
