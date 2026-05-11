"""Web UI: login, signup, dashboard, account, leaderboard, alliances.

All HTML rendering is delegated to Jinja2 templates in
backend/app/templates/. CSS lives in backend/app/static/main.css.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import httpx
from fastapi import APIRouter, Cookie, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.device import bind_token_to_code
from backend.app.config import get_settings
from backend.app.deps import DBSession
from backend.app.game.constants import BUILDING_LABELS, BuildingType
from backend.app.models.alliance import Alliance, AllianceMember, AllianceRole
from backend.app.models.building import Building
from backend.app.models.message import Message
from backend.app.models.planet import Planet
from backend.app.models.queue import BuildQueue
from backend.app.models.user import User
from backend.app.security import create_access_token, decode_token, hash_password, verify_password
from backend.app.services.resource_service import refresh_planet_resources
from backend.app.services.scoring_service import user_points
from backend.app.services.universe_service import (
    assign_starting_planet,
    ensure_default_universe,
    ensure_user_researches,
)
from backend.app.web_templates import templates

router = APIRouter(tags=["web"])

COOKIE_NAME = "ogame_token"


# ============================================================================
# Auth cookie helpers
# ============================================================================
async def _user_from_cookie(token: str | None, db: AsyncSession) -> User | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
        uid = int(payload["sub"])
    except (ValueError, KeyError):
        return None
    return await db.get(User, uid)


def _set_auth_cookie(resp: Response, token: str, request: Request | None = None) -> None:
    settings = get_settings()
    max_age_sec = max(30 * 24 * 3600, settings.jwt_expire_minutes * 60)
    secure = False
    if request is not None:
        if request.url.scheme == "https":
            secure = True
        elif request.headers.get("x-forwarded-proto") == "https":
            secure = True
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=max_age_sec,
        expires=max_age_sec,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


async def _alliance_for_user(db: AsyncSession, user_id: int) -> Alliance | None:
    m_res = await db.execute(
        select(AllianceMember).where(AllianceMember.user_id == user_id)
    )
    member = m_res.scalar_one_or_none()
    if member is None:
        return None
    return await db.get(Alliance, member.alliance_id)


def _is_admin(user: User) -> bool:
    return user.username == (get_settings().admin_username or "").strip()


async def _registered_count(db: AsyncSession) -> int:
    res = await db.execute(select(func.count()).select_from(User))
    return int(res.scalar() or 0)


# ============================================================================
# Lobby helpers
# ============================================================================
def _parse_lobby_servers(spec: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for entry in spec.split(","):
        entry = entry.strip()
        if not entry or "=" not in entry:
            continue
        name, url = entry.split("=", 1)
        out.append((name.strip(), url.strip()))
    return out


async def _poll_lobby_servers(servers: list[tuple[str, str]]) -> list[dict]:
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=2.0) as client:
        for name, url in servers:
            try:
                r = await client.get(f"{url.rstrip('/')}/stats")
                stats = r.json()
                reg = int(stats.get("registered", 0))
                cap = int(stats.get("max_users", 0) or 0)
                full = bool(stats.get("full", False))
                load_pct = (reg / cap * 100) if cap else 0
                color = "#ef4444" if full else ("#84cc16" if load_pct < 70 else "#fbbf24")
                out.append({
                    "name": name, "url": url,
                    "description": stats.get("description", ""),
                    "registered": reg, "max_users": cap, "full": full,
                    "color": color, "unreachable": False,
                })
            except Exception:
                out.append({
                    "name": name, "url": url,
                    "description": "",
                    "registered": 0, "max_users": 0, "full": False,
                    "color": "#525252", "unreachable": True,
                })
    return out


# ============================================================================
# Routes: root / login / signup / signin / logout / install
# ============================================================================
@router.get("/", response_class=HTMLResponse)
async def root(
    request: Request,
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is not None:
        return RedirectResponse("/dashboard", status_code=302)
    return await install_page(request, db)


@router.get("/install", response_class=HTMLResponse)
async def install_page(
    request: Request,
    db: DBSession,
) -> Response:
    settings = get_settings()
    host = request.headers.get("host", "sakusen.space")
    proto = "https" if request.url.scheme == "https" else "http"
    backend_url = f"{proto}://{host}"

    lobby_servers: list[dict] = []
    if settings.lobby_servers.strip():
        parsed = _parse_lobby_servers(settings.lobby_servers)
        lobby_servers = await _poll_lobby_servers(parsed)

    return templates.TemplateResponse(name="install.html", request=request, context={
            "request": request,
            "backend_url": backend_url,
            "lobby_servers": lobby_servers,
        },
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    db: DBSession,
    code: str | None = None,
    err: str | None = None,
    ok: str | None = None,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    if not code:
        user = await _user_from_cookie(ogame_token, db)
        if user is not None:
            return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(name="login.html", request=request, context={"request": request, "code": code, "err": err, "ok": ok},
    )


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(
    request: Request,
    db: DBSession,
    code: str | None = None,
    err: str | None = None,
    ok: str | None = None,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    if not code:
        user = await _user_from_cookie(ogame_token, db)
        if user is not None:
            return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(name="signup.html", request=request, context={"request": request, "code": code, "err": err, "ok": ok},
    )


@router.post("/signup")
async def signup_submit(
    request: Request,
    db: DBSession,
    username: Annotated[str, Form(min_length=3, max_length=32)],
    email: Annotated[str, Form()],
    password: Annotated[str, Form(min_length=6)],
    code: str | None = None,
) -> Response:
    settings = get_settings()
    total = await _registered_count(db)
    if total >= settings.server_max_users:
        return RedirectResponse(
            f"/signup?err=Server+is+full+({total}/{settings.server_max_users}).+Try+another+server.",
            status_code=303,
        )

    existing = await db.execute(
        select(User).where(or_(User.username == username, User.email == email))
    )
    if existing.scalar_one_or_none() is not None:
        qs = f"&code={code}" if code else ""
        return RedirectResponse(
            f"/signup?err=That+username+or+email+is+already+taken{qs}", status_code=303
        )

    universe = await ensure_default_universe(db)
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(password),
        current_universe_id=universe.id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    await ensure_user_researches(db, user.id)
    await db.commit()
    await assign_starting_planet(db, user.id, universe)

    token = create_access_token(user.id)

    if code:
        bound = await bind_token_to_code(db, code=code, token=token, user_id=user.id)
        if not bound:
            return RedirectResponse(
                "/login?err=Auth+code+invalid+or+expired.+Restart+sakusen+in+terminal.",
                status_code=303,
            )
        return templates.TemplateResponse(name="terminal_success.html", request=request, context={"request": request, "username": username},
        )

    resp = RedirectResponse("/dashboard", status_code=303)
    _set_auth_cookie(resp, token, request)
    return resp


@router.post("/signin")
async def signin_submit(
    request: Request,
    db: DBSession,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    code: str | None = None,
) -> Response:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        qs = f"&code={code}" if code else ""
        return RedirectResponse(
            f"/login?err=Wrong+username+or+password{qs}", status_code=303
        )

    token = create_access_token(user.id)

    if code:
        bound = await bind_token_to_code(db, code=code, token=token, user_id=user.id)
        if not bound:
            return RedirectResponse(
                "/login?err=Auth+code+invalid+or+expired.+Restart+sakusen+in+terminal.",
                status_code=303,
            )
        return templates.TemplateResponse(name="terminal_success.html", request=request, context={"request": request, "username": user.username},
        )

    resp = RedirectResponse("/dashboard", status_code=303)
    _set_auth_cookie(resp, token, request)
    return resp


@router.get("/logout")
async def logout() -> Response:
    resp = RedirectResponse("/login?ok=Signed+out", status_code=303)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


# ============================================================================
# /me - account page
# ============================================================================
@router.get("/me", response_class=HTMLResponse)
async def me_page(
    request: Request,
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)

    planet_res = await db.execute(
        select(Planet).where(Planet.owner_user_id == user.id).order_by(Planet.id)
    )
    planets = list(planet_res.scalars().all())
    alliance = await _alliance_for_user(db, user.id)

    return templates.TemplateResponse(name="me.html", request=request, context={
            "request": request,
            "user": user,
            "planets": planets,
            "alliance": alliance,
            "is_admin": _is_admin(user),
            "server_name": get_settings().server_name,
        },
    )


# ============================================================================
# /dashboard
# ============================================================================
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
    planet_id: int | None = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)

    planet_res = await db.execute(
        select(Planet).where(Planet.owner_user_id == user.id).order_by(Planet.id)
    )
    planets = list(planet_res.scalars().all())
    if not planets:
        return HTMLResponse(
            "<h2>No planets</h2><p>Contact the operator.</p><a href='/logout'>logout</a>",
            status_code=200,
        )

    selected = planets[0]
    if planet_id is not None:
        for p in planets:
            if p.id == planet_id:
                selected = p
                break

    planet, report = await refresh_planet_resources(db, selected.id)
    await db.commit()
    await db.refresh(planet)

    bld_res = await db.execute(
        select(Building).where(Building.planet_id == planet.id)
    )
    buildings_raw = list(bld_res.scalars().all())
    # Sort by level desc, then by display label
    buildings = []
    for b in buildings_raw:
        try:
            label = BUILDING_LABELS[BuildingType(b.building_type)]
        except (ValueError, KeyError):
            label = b.building_type
        buildings.append({"label": label, "level": b.level})
    buildings.sort(key=lambda r: (-r["level"], r["label"]))
    built_count = sum(1 for b in buildings if b["level"] > 0)

    queue_res = await db.execute(
        select(BuildQueue)
        .where(
            BuildQueue.planet_id == planet.id,
            BuildQueue.cancelled.is_(False),
            BuildQueue.applied.is_(False),
        )
        .order_by(BuildQueue.finished_at)
    )
    active_queue = list(queue_res.scalars().all())

    logs_res = await db.execute(
        select(BuildQueue)
        .where(BuildQueue.planet_id == planet.id, BuildQueue.applied.is_(True))
        .order_by(desc(BuildQueue.finished_at))
        .limit(15)
    )
    logs = list(logs_res.scalars().all())

    unread_res = await db.execute(
        select(func.count())
        .select_from(Message)
        .where(and_(Message.recipient_id == user.id, Message.read.is_(False)))
    )
    unread_count = int(unread_res.scalar() or 0)
    registered_count = await _registered_count(db)
    alliance = await _alliance_for_user(db, user.id)
    settings = get_settings()

    return templates.TemplateResponse(name="dashboard.html", request=request, context={
            "request": request,
            "user": user,
            "current_planet": planet,
            "all_planets": planets,
            "production": report,
            "buildings": buildings,
            "built_count": built_count,
            "active_queue": active_queue,
            "logs": logs,
            "unread": unread_count,
            "registered_count": registered_count,
            "server_name": settings.server_name,
            "server_max_users": settings.server_max_users,
            "lobby_url": settings.lobby_url,
            "is_admin": _is_admin(user),
            "alliance_tag": alliance.tag if alliance else None,
        },
    )


# ============================================================================
# /leaderboard
# ============================================================================
@router.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(
    request: Request,
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)

    users_res = await db.execute(select(User).order_by(User.id))
    users = list(users_res.scalars().all())

    member_res = await db.execute(
        select(AllianceMember.user_id, Alliance.tag)
        .join(Alliance, Alliance.id == AllianceMember.alliance_id)
    )
    alliance_by_user: dict[int, str] = {uid: tag for uid, tag in member_res.all()}

    scored: list[tuple[User, dict]] = []
    for u in users:
        pts = await user_points(db, u.id)
        scored.append((u, pts))
    scored.sort(key=lambda t: t[1]["total_points"], reverse=True)

    rows = []
    my_rank: int | None = None
    my_points: int | None = None
    for i, (u, pts) in enumerate(scored, start=1):
        if u.id == user.id:
            my_rank = i
            my_points = pts["total_points"]
        if i <= 100:
            rows.append({
                "rank": i,
                "user_id": u.id,
                "username": u.username,
                "alliance_tag": alliance_by_user.get(u.id),
                "is_me": u.id == user.id,
                **pts,
            })

    return templates.TemplateResponse(name="leaderboard.html", request=request, context={
            "request": request,
            "rows": rows,
            "total_players": len(scored),
            "my_rank": my_rank,
            "my_points": my_points or 0,
            "server_name": get_settings().server_name,
        },
    )


# ============================================================================
# /alliances
# ============================================================================
@router.get("/alliances", response_class=HTMLResponse)
async def alliances_page(
    request: Request,
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
    err: str | None = None,
    ok: str | None = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)

    my_alliance = await _alliance_for_user(db, user.id)

    all_res = await db.execute(select(Alliance).order_by(desc(Alliance.id)))
    alliances_raw = list(all_res.scalars().all())

    # Build display rows with member counts + founder names
    alliances = []
    for a in alliances_raw:
        count_res = await db.execute(
            select(func.count()).select_from(AllianceMember)
            .where(AllianceMember.alliance_id == a.id)
        )
        member_count = int(count_res.scalar() or 0)
        founder = await db.get(User, a.founder_id)
        is_member = my_alliance is not None and my_alliance.id == a.id
        alliances.append({
            "id": a.id, "tag": a.tag, "name": a.name,
            "description": a.description,
            "member_count": member_count,
            "founder_username": founder.username if founder else "?",
            "is_member": is_member,
        })

    return templates.TemplateResponse(name="alliances.html", request=request, context={
            "request": request,
            "user": user,
            "my_alliance": my_alliance,
            "alliances": alliances,
            "err": err,
            "ok": ok,
            "server_name": get_settings().server_name,
        },
    )


@router.post("/alliances/create")
async def alliance_create_form(
    db: DBSession,
    tag: Annotated[str, Form(min_length=2, max_length=6, pattern=r"^[A-Za-z0-9]+$")],
    name: Annotated[str, Form(min_length=3, max_length=64)],
    description: Annotated[str, Form(max_length=500)] = "",
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)

    existing_m = await db.execute(
        select(AllianceMember).where(AllianceMember.user_id == user.id)
    )
    if existing_m.scalar_one_or_none() is not None:
        return RedirectResponse(
            "/alliances?err=Leave+your+current+alliance+first", status_code=303
        )

    a = Alliance(
        tag=tag.upper(), name=name, description=description,
        founder_id=user.id,
    )
    db.add(a)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return RedirectResponse(
            "/alliances?err=Tag+or+name+already+taken", status_code=303
        )
    db.add(AllianceMember(
        alliance_id=a.id, user_id=user.id, role=AllianceRole.FOUNDER.value
    ))
    await db.commit()
    return RedirectResponse(f"/alliances/{a.tag}", status_code=303)


@router.get("/alliances/{tag}", response_class=HTMLResponse)
async def alliance_detail_page(
    tag: str,
    request: Request,
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)

    a_res = await db.execute(select(Alliance).where(Alliance.tag == tag.upper()))
    a = a_res.scalar_one_or_none()
    if a is None:
        return HTMLResponse("alliance not found", status_code=404)

    founder = await db.get(User, a.founder_id)
    my_alliance = await _alliance_for_user(db, user.id)
    is_member = my_alliance is not None and my_alliance.id == a.id

    m_res = await db.execute(
        select(AllianceMember, User)
        .join(User, User.id == AllianceMember.user_id)
        .where(AllianceMember.alliance_id == a.id)
        .order_by(AllianceMember.joined_at)
    )
    members = []
    for m, u in m_res.all():
        pts = await user_points(db, u.id)
        members.append({
            "user_id": u.id, "username": u.username,
            "role": m.role, "joined_at": m.joined_at,
            "is_me": u.id == user.id,
            "total_points": pts["total_points"],
        })

    return templates.TemplateResponse(name="alliance_detail.html", request=request, context={
            "request": request,
            "alliance": a,
            "members": members,
            "founder_username": founder.username if founder else "?",
            "my_alliance": my_alliance,
            "is_member": is_member,
            "server_name": get_settings().server_name,
        },
    )


@router.post("/alliances/{tag}/join")
async def alliance_join_form(
    tag: str,
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)

    existing_m = await db.execute(
        select(AllianceMember).where(AllianceMember.user_id == user.id)
    )
    if existing_m.scalar_one_or_none() is not None:
        return RedirectResponse(
            "/alliances?err=Leave+your+current+alliance+first", status_code=303
        )

    a_res = await db.execute(select(Alliance).where(Alliance.tag == tag.upper()))
    a = a_res.scalar_one_or_none()
    if a is None:
        return RedirectResponse("/alliances?err=Alliance+not+found", status_code=303)

    db.add(AllianceMember(
        alliance_id=a.id, user_id=user.id, role=AllianceRole.MEMBER.value
    ))
    await db.commit()
    return RedirectResponse(f"/alliances/{a.tag}", status_code=303)


@router.post("/alliances/{tag}/leave")
async def alliance_leave_form(
    tag: str,
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)

    a_res = await db.execute(select(Alliance).where(Alliance.tag == tag.upper()))
    a = a_res.scalar_one_or_none()
    if a is None:
        return RedirectResponse("/alliances?err=Alliance+not+found", status_code=303)

    m_res = await db.execute(
        select(AllianceMember).where(
            AllianceMember.alliance_id == a.id,
            AllianceMember.user_id == user.id,
        )
    )
    member = m_res.scalar_one_or_none()
    if member is None:
        return RedirectResponse("/alliances?err=Not+a+member", status_code=303)

    count_res = await db.execute(
        select(func.count()).select_from(AllianceMember)
        .where(AllianceMember.alliance_id == a.id)
    )
    total_members = int(count_res.scalar() or 0)
    if member.role == AllianceRole.FOUNDER.value and total_members > 1:
        return RedirectResponse(
            f"/alliances/{tag}?err=Founder+cannot+leave+with+members+remaining",
            status_code=303,
        )

    await db.delete(member)
    if total_members <= 1:
        await db.delete(a)
    await db.commit()
    return RedirectResponse("/alliances?ok=Left+alliance", status_code=303)
