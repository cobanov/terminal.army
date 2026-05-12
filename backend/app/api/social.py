"""Players list + Messages (basic player-to-player communication)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, asc, case, desc, func, or_, select

from backend.app.deps import CurrentUser, DBSession
from backend.app.models.message import Message
from backend.app.models.user import User

router = APIRouter(tags=["social"])


class PlayerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class MessageSend(BaseModel):
    recipient_username: str = Field(min_length=3, max_length=32)
    body: str = Field(min_length=1, max_length=2000)


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender_id: int
    sender_username: str
    recipient_id: int
    recipient_username: str
    body: str
    created_at: datetime
    read: bool


@router.get("/api/players", response_model=list[PlayerRead])
async def list_players(user: CurrentUser, db: DBSession) -> list[PlayerRead]:
    """List all players in the same universe.

    Lives at /api/players so the web /players HTML page can own the
    short URL.
    """
    result = await db.execute(
        select(User)
        .where(User.current_universe_id == user.current_universe_id)
        .order_by(User.username)
    )
    return [PlayerRead.model_validate(u) for u in result.scalars().all()]


@router.post("/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
async def send_message(body: MessageSend, user: CurrentUser, db: DBSession) -> MessageRead:
    result = await db.execute(select(User).where(User.username == body.recipient_username))
    recipient = result.scalar_one_or_none()
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="recipient not found")
    if recipient.id == user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="cannot message yourself"
        )

    msg = Message(
        sender_id=user.id,
        recipient_id=recipient.id,
        body=body.body,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    return MessageRead(
        id=msg.id,
        sender_id=msg.sender_id,
        sender_username=user.username,
        recipient_id=msg.recipient_id,
        recipient_username=recipient.username,
        body=msg.body,
        created_at=msg.created_at,
        read=msg.read,
    )


@router.get("/messages", response_model=list[MessageRead])
async def inbox(
    user: CurrentUser,
    db: DBSession,
    unread_only: bool = False,
    limit: int = 50,
) -> list[MessageRead]:
    """Inbox: messages received by the current user."""
    sender_u = User.__table__.alias("sender_u")
    recipient_u = User.__table__.alias("recipient_u")
    q = (
        select(
            Message.id,
            Message.sender_id,
            Message.recipient_id,
            Message.body,
            Message.created_at,
            Message.read,
            sender_u.c.username.label("sender_username"),
            recipient_u.c.username.label("recipient_username"),
        )
        .join(sender_u, sender_u.c.id == Message.sender_id)
        .join(recipient_u, recipient_u.c.id == Message.recipient_id)
        .where(Message.recipient_id == user.id)
        .order_by(desc(Message.created_at))
        .limit(limit)
    )
    if unread_only:
        q = q.where(Message.read.is_(False))
    result = await db.execute(q)
    rows = result.all()
    out: list[MessageRead] = []
    for row in rows:
        out.append(
            MessageRead(
                id=row.id,
                sender_id=row.sender_id,
                sender_username=row.sender_username,
                recipient_id=row.recipient_id,
                recipient_username=row.recipient_username,
                body=row.body,
                created_at=row.created_at,
                read=row.read,
            )
        )
    return out


@router.get("/messages/unread-count")
async def unread_count(user: CurrentUser, db: DBSession) -> dict[str, int]:
    result = await db.execute(
        select(func.count())
        .select_from(Message)
        .where(and_(Message.recipient_id == user.id, Message.read.is_(False)))
    )
    return {"count": int(result.scalar() or 0)}


@router.post("/messages/{message_id}/read", response_model=MessageRead)
async def mark_read(message_id: int, user: CurrentUser, db: DBSession) -> MessageRead:
    msg = await db.get(Message, message_id)
    if msg is None or msg.recipient_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="message not found")
    msg.read = True
    await db.commit()
    await db.refresh(msg)

    sender = await db.get(User, msg.sender_id)
    return MessageRead(
        id=msg.id,
        sender_id=msg.sender_id,
        sender_username=sender.username if sender else "?",
        recipient_id=msg.recipient_id,
        recipient_username=user.username,
        body=msg.body,
        created_at=msg.created_at,
        read=msg.read,
    )


# ---------- Threaded conversations ----------------------------------------
class ThreadSummary(BaseModel):
    other_username: str
    other_id: int
    last_at: datetime
    last_preview: str
    last_from_me: bool
    unread_count: int


@router.get("/messages/threads", response_model=list[ThreadSummary])
async def list_threads(user: CurrentUser, db: DBSession) -> list[ThreadSummary]:
    """List of distinct conversation partners with last message preview."""
    # Subquery: for each message, the "other" user_id (sender if I'm recipient, else recipient)
    other_id = case(
        (Message.sender_id == user.id, Message.recipient_id),
        else_=Message.sender_id,
    ).label("other_id")

    # Aggregate per "other" user
    sub = (
        select(
            other_id,
            func.max(Message.created_at).label("last_at"),
            func.sum(
                case(
                    (and_(Message.recipient_id == user.id, Message.read.is_(False)), 1),
                    else_=0,
                )
            ).label("unread_count"),
        )
        .where(or_(Message.sender_id == user.id, Message.recipient_id == user.id))
        .group_by(other_id)
        .subquery()
    )

    # Join with User to get username + last message body
    threads_q = (
        select(
            sub.c.other_id,
            User.username,
            sub.c.last_at,
            sub.c.unread_count,
        )
        .join(User, User.id == sub.c.other_id)
        .order_by(desc(sub.c.last_at))
    )
    rows = (await db.execute(threads_q)).all()

    out: list[ThreadSummary] = []
    for row in rows:
        last_msg_q = (
            select(Message)
            .where(
                or_(
                    and_(Message.sender_id == user.id, Message.recipient_id == row.other_id),
                    and_(Message.sender_id == row.other_id, Message.recipient_id == user.id),
                )
            )
            .order_by(desc(Message.created_at))
            .limit(1)
        )
        last = (await db.execute(last_msg_q)).scalar_one_or_none()
        preview = (
            (last.body[:60] + "...")
            if last and len(last.body) > 60
            else (last.body if last else "")
        )
        out.append(
            ThreadSummary(
                other_username=row.username,
                other_id=row.other_id,
                last_at=row.last_at,
                last_preview=preview,
                last_from_me=(last.sender_id == user.id) if last else False,
                unread_count=int(row.unread_count or 0),
            )
        )
    return out


@router.get("/messages/with/{username}", response_model=list[MessageRead])
async def conversation(
    username: str,
    user: CurrentUser,
    db: DBSession,
    limit: int = 100,
) -> list[MessageRead]:
    """All messages between the current user and `username`, oldest first."""
    other_q = await db.execute(select(User).where(User.username == username))
    other = other_q.scalar_one_or_none()
    if other is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    sender_u = User.__table__.alias("sender_u")
    recipient_u = User.__table__.alias("recipient_u")
    q = (
        select(
            Message.id,
            Message.sender_id,
            Message.recipient_id,
            Message.body,
            Message.created_at,
            Message.read,
            sender_u.c.username.label("sender_username"),
            recipient_u.c.username.label("recipient_username"),
        )
        .join(sender_u, sender_u.c.id == Message.sender_id)
        .join(recipient_u, recipient_u.c.id == Message.recipient_id)
        .where(
            or_(
                and_(Message.sender_id == user.id, Message.recipient_id == other.id),
                and_(Message.sender_id == other.id, Message.recipient_id == user.id),
            )
        )
        .order_by(asc(Message.created_at))
        .limit(limit)
    )
    rows = (await db.execute(q)).all()

    # Auto-mark received messages as read
    to_mark = [r.id for r in rows if r.recipient_id == user.id and not r.read]
    if to_mark:
        for mid in to_mark:
            m = await db.get(Message, mid)
            if m is not None:
                m.read = True
        await db.commit()

    return [
        MessageRead(
            id=row.id,
            sender_id=row.sender_id,
            sender_username=row.sender_username,
            recipient_id=row.recipient_id,
            recipient_username=row.recipient_username,
            body=row.body,
            created_at=row.created_at,
            read=True if row.id in to_mark else row.read,
        )
        for row in rows
    ]
