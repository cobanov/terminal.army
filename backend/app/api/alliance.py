"""Alliance JSON API (for the TUI client).

Endpoints:
    GET    /alliances                  list with member counts
    POST   /alliances                  create (body: tag, name, description)
    GET    /alliances/{tag}            detail + members
    POST   /alliances/{tag}/join       join (must not be in another)
    POST   /alliances/{tag}/leave      leave (founder cannot leave if others remain)
    GET    /me/alliance                my alliance (or 404)
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.deps import CurrentUser, DBSession
from backend.app.models.alliance import Alliance, AllianceMember, AllianceRole
from backend.app.models.user import User

router = APIRouter(tags=["alliance"])


class AllianceCreate(BaseModel):
    tag: str = Field(min_length=2, max_length=6, pattern=r"^[A-Za-z0-9]+$")
    name: str = Field(min_length=3, max_length=64)
    description: str = Field(default="", max_length=500)


class AllianceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tag: str
    name: str
    description: str
    founder_id: int
    founder_username: str
    member_count: int
    created_at: datetime


class AllianceMemberRead(BaseModel):
    user_id: int
    username: str
    role: str
    joined_at: datetime


class AllianceDetail(AllianceRead):
    members: list[AllianceMemberRead] = []


async def _row_to_read(db: AsyncSession, a: Alliance) -> AllianceRead:
    count_res = await db.execute(
        select(func.count()).select_from(AllianceMember).where(AllianceMember.alliance_id == a.id)
    )
    member_count = int(count_res.scalar() or 0)
    founder = await db.get(User, a.founder_id)
    return AllianceRead(
        id=a.id,
        tag=a.tag,
        name=a.name,
        description=a.description,
        founder_id=a.founder_id,
        founder_username=founder.username if founder else "?",
        member_count=member_count,
        created_at=a.created_at,
    )


@router.get("/alliances", response_model=list[AllianceRead])
async def list_alliances(_user: CurrentUser, db: DBSession) -> list[AllianceRead]:
    res = await db.execute(select(Alliance).order_by(desc(Alliance.id)))
    out = []
    for a in res.scalars().all():
        out.append(await _row_to_read(db, a))
    return out


@router.post("/alliances", response_model=AllianceRead, status_code=status.HTTP_201_CREATED)
async def create_alliance(body: AllianceCreate, user: CurrentUser, db: DBSession) -> AllianceRead:
    # User must not already be in an alliance
    existing_m = await db.execute(select(AllianceMember).where(AllianceMember.user_id == user.id))
    if existing_m.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="leave your current alliance first")

    tag_upper = body.tag.upper()
    alliance = Alliance(
        tag=tag_upper,
        name=body.name,
        description=body.description,
        founder_id=user.id,
    )
    db.add(alliance)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="tag or name already taken") from exc

    db.add(
        AllianceMember(alliance_id=alliance.id, user_id=user.id, role=AllianceRole.FOUNDER.value)
    )
    await db.commit()
    await db.refresh(alliance)
    return await _row_to_read(db, alliance)


async def _alliance_by_tag(db: AsyncSession, tag: str) -> Alliance:
    res = await db.execute(select(Alliance).where(Alliance.tag == tag.upper()))
    a = res.scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="alliance not found")
    return a


@router.get("/alliances/{tag}", response_model=AllianceDetail)
async def get_alliance(tag: str, _user: CurrentUser, db: DBSession) -> AllianceDetail:
    a = await _alliance_by_tag(db, tag)
    base = await _row_to_read(db, a)
    m_res = await db.execute(
        select(AllianceMember, User)
        .join(User, User.id == AllianceMember.user_id)
        .where(AllianceMember.alliance_id == a.id)
        .order_by(AllianceMember.joined_at)
    )
    members = [
        AllianceMemberRead(
            user_id=m.user_id,
            username=u.username,
            role=m.role,
            joined_at=m.joined_at,
        )
        for m, u in m_res.all()
    ]
    return AllianceDetail(**base.model_dump(), members=members)


@router.post("/alliances/{tag}/join", response_model=AllianceRead)
async def join_alliance(tag: str, user: CurrentUser, db: DBSession) -> AllianceRead:
    existing_m = await db.execute(select(AllianceMember).where(AllianceMember.user_id == user.id))
    if existing_m.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="leave your current alliance first")

    a = await _alliance_by_tag(db, tag)
    db.add(AllianceMember(alliance_id=a.id, user_id=user.id, role=AllianceRole.MEMBER.value))
    await db.commit()
    return await _row_to_read(db, a)


@router.post("/alliances/{tag}/leave")
async def leave_alliance(tag: str, user: CurrentUser, db: DBSession) -> dict:
    a = await _alliance_by_tag(db, tag)
    m_res = await db.execute(
        select(AllianceMember).where(
            AllianceMember.alliance_id == a.id,
            AllianceMember.user_id == user.id,
        )
    )
    member = m_res.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=400, detail="not a member")

    # If founder leaves while others remain, disallow (founder must transfer
    # or dissolve first). MVP: if last member, alliance auto-deletes.
    count_res = await db.execute(
        select(func.count()).select_from(AllianceMember).where(AllianceMember.alliance_id == a.id)
    )
    total_members = int(count_res.scalar() or 0)
    if member.role == AllianceRole.FOUNDER.value and total_members > 1:
        raise HTTPException(
            status_code=400,
            detail="founder cannot leave; transfer or dissolve first",
        )

    await db.delete(member)
    if total_members <= 1:
        await db.delete(a)
    await db.commit()
    return {"left": True}


@router.get("/me/alliance", response_model=AllianceDetail | None)
async def my_alliance(user: CurrentUser, db: DBSession) -> AllianceDetail | None:
    m_res = await db.execute(select(AllianceMember).where(AllianceMember.user_id == user.id))
    member = m_res.scalar_one_or_none()
    if member is None:
        return None
    a = await db.get(Alliance, member.alliance_id)
    if a is None:
        return None
    return await get_alliance(a.tag, user, db)
