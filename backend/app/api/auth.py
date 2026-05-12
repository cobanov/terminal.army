from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_, select

from backend.app.deps import CurrentUser, DBSession
from backend.app.models.user import User
from backend.app.rate_limit import limiter
from backend.app.schemas.auth import RegisterRequest, TokenResponse, UserPublic
from backend.app.security import create_access_token, hash_password, verify_password
from backend.app.services.universe_service import (
    assign_starting_planet,
    ensure_default_universe,
    ensure_user_researches,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: DBSession) -> UserPublic:
    existing = await db.execute(
        select(User).where(or_(User.username == body.username, User.email == body.email))
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="username or email already taken"
        )

    universe = await ensure_default_universe(db)

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        current_universe_id=universe.id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await ensure_user_researches(db, user.id)
    await db.commit()

    await assign_starting_planet(db, user.id, universe)

    return UserPublic.model_validate(user)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DBSession,
) -> TokenResponse:
    result = await db.execute(select(User).where(User.username == form.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    token = create_access_token(user.id)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserPublic)
async def me(user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(user)
