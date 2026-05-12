"""Alliance JSON API (for the TUI client).

Endpoints:
    GET    /alliances                          list with member counts
    POST   /alliances                          create (body: tag, name, description)
    GET    /alliances/{tag}                    detail + members
    POST   /alliances/{tag}/join               apply (creates a pending request)
    POST   /alliances/{tag}/leave              leave (founder dissolves alliance)
    GET    /alliances/{tag}/requests           founder only: list pending applicants
    POST   /alliances/{tag}/requests/{username}/approve   founder approves
    POST   /alliances/{tag}/requests/{username}/reject    founder rejects
    DELETE /me/alliance-request                withdraw my own pending request
    GET    /me/alliance-request                inspect my pending request
    GET    /me/alliance                        my alliance (or null)
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.deps import CurrentUser, DBSession
from backend.app.models.alliance import (
    Alliance,
    AllianceJoinRequest,
    AllianceMember,
    AllianceRole,
)
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


class JoinRequestBody(BaseModel):
    message: str = Field(default="", max_length=500)


class JoinRequestRead(BaseModel):
    alliance_id: int
    alliance_tag: str
    alliance_name: str
    user_id: int
    username: str
    message: str
    created_at: datetime


@router.post(
    "/alliances/{tag}/join",
    response_model=JoinRequestRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_join_alliance(
    tag: str,
    user: CurrentUser,
    db: DBSession,
    body: JoinRequestBody | None = None,
) -> JoinRequestRead:
    """Submit a join request. The founder must approve before membership."""
    existing_m = await db.execute(select(AllianceMember).where(AllianceMember.user_id == user.id))
    if existing_m.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="leave your current alliance first")

    # One pending request at a time across all alliances.
    existing_r = await db.execute(
        select(AllianceJoinRequest).where(AllianceJoinRequest.user_id == user.id)
    )
    if existing_r.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="you already have a pending alliance request — withdraw it first",
        )

    a = await _alliance_by_tag(db, tag)
    req = AllianceJoinRequest(
        alliance_id=a.id,
        user_id=user.id,
        message=(body.message if body else ""),
    )
    db.add(req)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="request already pending for this alliance"
        ) from exc
    await db.refresh(req)
    return JoinRequestRead(
        alliance_id=a.id,
        alliance_tag=a.tag,
        alliance_name=a.name,
        user_id=user.id,
        username=user.username,
        message=req.message,
        created_at=req.created_at,
    )


@router.get("/alliances/{tag}/requests", response_model=list[JoinRequestRead])
async def list_join_requests(
    tag: str, user: CurrentUser, db: DBSession
) -> list[JoinRequestRead]:
    """Founder-only: list pending applicants for the alliance."""
    a = await _alliance_by_tag(db, tag)
    if a.founder_id != user.id:
        raise HTTPException(status_code=403, detail="only the founder can view requests")

    res = await db.execute(
        select(AllianceJoinRequest, User)
        .join(User, User.id == AllianceJoinRequest.user_id)
        .where(AllianceJoinRequest.alliance_id == a.id)
        .order_by(AllianceJoinRequest.created_at)
    )
    return [
        JoinRequestRead(
            alliance_id=a.id,
            alliance_tag=a.tag,
            alliance_name=a.name,
            user_id=u.id,
            username=u.username,
            message=r.message,
            created_at=r.created_at,
        )
        for r, u in res.all()
    ]


async def _founder_request(
    db: AsyncSession, tag: str, founder: User, username: str
) -> tuple[Alliance, AllianceJoinRequest, User]:
    a = await _alliance_by_tag(db, tag)
    if a.founder_id != founder.id:
        raise HTTPException(status_code=403, detail="only the founder can decide requests")
    u_res = await db.execute(select(User).where(User.username == username))
    applicant = u_res.scalar_one_or_none()
    if applicant is None:
        raise HTTPException(status_code=404, detail="user not found")
    r_res = await db.execute(
        select(AllianceJoinRequest).where(
            AllianceJoinRequest.alliance_id == a.id,
            AllianceJoinRequest.user_id == applicant.id,
        )
    )
    req = r_res.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="no pending request from that user")
    return a, req, applicant


@router.post("/alliances/{tag}/requests/{username}/approve", response_model=AllianceRead)
async def approve_join_request(
    tag: str, username: str, user: CurrentUser, db: DBSession
) -> AllianceRead:
    a, req, applicant = await _founder_request(db, tag, user, username)

    # If the applicant joined some other alliance after applying, reject quietly.
    in_other = await db.execute(
        select(AllianceMember).where(AllianceMember.user_id == applicant.id)
    )
    if in_other.scalar_one_or_none() is not None:
        await db.delete(req)
        await db.commit()
        raise HTTPException(
            status_code=409, detail=f"{username} already belongs to an alliance"
        )

    db.add(
        AllianceMember(
            alliance_id=a.id, user_id=applicant.id, role=AllianceRole.MEMBER.value
        )
    )
    await db.delete(req)
    await db.commit()
    return await _row_to_read(db, a)


@router.post("/alliances/{tag}/requests/{username}/reject")
async def reject_join_request(
    tag: str, username: str, user: CurrentUser, db: DBSession
) -> dict[str, bool]:
    _, req, _ = await _founder_request(db, tag, user, username)
    await db.delete(req)
    await db.commit()
    return {"rejected": True}


@router.get("/me/alliance-request", response_model=JoinRequestRead | None)
async def my_alliance_request(
    user: CurrentUser, db: DBSession
) -> JoinRequestRead | None:
    res = await db.execute(
        select(AllianceJoinRequest, Alliance)
        .join(Alliance, Alliance.id == AllianceJoinRequest.alliance_id)
        .where(AllianceJoinRequest.user_id == user.id)
    )
    row = res.one_or_none()
    if row is None:
        return None
    req, a = row
    return JoinRequestRead(
        alliance_id=a.id,
        alliance_tag=a.tag,
        alliance_name=a.name,
        user_id=user.id,
        username=user.username,
        message=req.message,
        created_at=req.created_at,
    )


@router.delete("/me/alliance-request")
async def withdraw_alliance_request(
    user: CurrentUser, db: DBSession
) -> dict[str, bool]:
    res = await db.execute(
        select(AllianceJoinRequest).where(AllianceJoinRequest.user_id == user.id)
    )
    req = res.scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="no pending request")
    await db.delete(req)
    await db.commit()
    return {"withdrawn": True}


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
