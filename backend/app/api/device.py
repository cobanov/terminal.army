"""Device authorization flow (CLI <-> browser).

CLI:
  POST /auth/start             -> returns auth_code (and polling info)
  POST /auth/poll {auth_code}  -> 202 pending, or 200 + token

Browser (HTML):
  GET  /login?code=AUTH_CODE   -> signup/signin form (existing /signup HTML)
  POST /signup?code=AUTH_CODE  -> on success, binds JWT to auth_code, shows success page
  POST /signin?code=AUTH_CODE  -> same
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.deps import DBSession
from backend.app.models.device_session import DeviceSession
from backend.app.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["auth-device"])


DEVICE_TTL_SECONDS = 600  # 10 minutes
POLLING_INTERVAL_SECONDS = 2


class StartResponse(BaseModel):
    auth_code: str
    expires_in: int
    polling_interval: int


class PollRequest(BaseModel):
    auth_code: str


class PollResponse(BaseModel):
    token: str


@router.post("/start", response_model=StartResponse)
@limiter.limit("20/minute")
async def device_start(request: Request, db: DBSession) -> StartResponse:
    # 22-char URL-safe random code (clean, no path issues)
    code = secrets.token_urlsafe(16)
    now = datetime.now(UTC)
    session = DeviceSession(
        code=code,
        token=None,
        user_id=None,
        created_at=now,
        expires_at=now + timedelta(seconds=DEVICE_TTL_SECONDS),
    )
    db.add(session)
    await db.commit()
    return StartResponse(
        auth_code=code,
        expires_in=DEVICE_TTL_SECONDS,
        polling_interval=POLLING_INTERVAL_SECONDS,
    )


@router.post("/poll")
async def device_poll(body: PollRequest, db: DBSession) -> PollResponse:
    result = await db.execute(select(DeviceSession).where(DeviceSession.code == body.auth_code))
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="auth code not found")

    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        await db.delete(session)
        await db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="auth code expired")

    if session.token is None:
        # 202 = still pending
        raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail="pending")

    token = session.token
    # One-time use: consume the row
    await db.delete(session)
    await db.commit()
    return PollResponse(token=token)


async def bind_token_to_code(db: AsyncSession, *, code: str, token: str, user_id: int) -> bool:
    """Used internally by signup/signin views to attach a token to a device code.

    Returns True if bound, False if code invalid/expired/already-used.
    """
    result = await db.execute(select(DeviceSession).where(DeviceSession.code == code))
    session = result.scalar_one_or_none()
    if session is None:
        return False
    expires_at = session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        return False
    if session.token is not None:
        return False
    session.token = token
    session.user_id = user_id
    await db.commit()
    return True
