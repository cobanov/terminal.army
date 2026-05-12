"""Web UI: login, signup, dashboard, account, leaderboard, alliances.

All HTML rendering is delegated to Jinja2 templates in
backend/app/templates/. CSS lives in backend/app/static/main.css.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.device import bind_token_to_code
from backend.app.config import get_settings
from backend.app.deps import DBSession
from backend.app.game.constants import (
    BUILDING_LABELS,
    DEFENSE_LABELS,
    FACILITY_BUILDINGS,
    RESOURCE_BUILDINGS,
    BuildingType,
    DefenseType,
)
from backend.app.models.alliance import (
    Alliance,
    AllianceJoinRequest,
    AllianceMember,
    AllianceRole,
)
from backend.app.models.building import Building
from backend.app.models.message import Message
from backend.app.models.planet import Planet
from backend.app.models.queue import BuildQueue
from backend.app.models.ship import PlanetDefense
from backend.app.models.user import User
from backend.app.presence import online_count
from backend.app.rate_limit import limiter
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
    user = await db.get(User, uid)
    if user is not None:
        from backend.app.presence import touch

        touch(user.id)
    return user


def _set_auth_cookie(resp: Response, token: str, request: Request | None = None) -> None:
    settings = get_settings()
    max_age_sec = max(30 * 24 * 3600, settings.jwt_expire_minutes * 60)
    # In prod we always issue a Secure cookie. The backend sits behind a
    # TLS-terminating proxy (Cloudflare, Caddy, etc.) so the first hop is
    # always https; even if X-Forwarded-Proto is missing or stripped, we
    # never want to fall back to an unsecured cookie on a public deploy.
    secure = settings.env == "prod"
    if not secure and request is not None:
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
    m_res = await db.execute(select(AllianceMember).where(AllianceMember.user_id == user_id))
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
# Landing page rankings helper
# ============================================================================
async def _landing_rankings(db: AsyncSession, limit: int = 20) -> list[dict]:
    """Top N players for the install landing page. Unauthenticated."""
    users_res = await db.execute(select(User).order_by(User.id))
    users = list(users_res.scalars().all())

    member_res = await db.execute(
        select(AllianceMember.user_id, Alliance.tag).join(
            Alliance, Alliance.id == AllianceMember.alliance_id
        )
    )
    alliance_by_user: dict[int, str] = {uid: tag for uid, tag in member_res.all()}

    scored: list[tuple[User, int]] = []
    for u in users:
        pts = await user_points(db, u.id)
        scored.append((u, pts["total_points"]))
    scored.sort(key=lambda t: t[1], reverse=True)

    return [
        {
            "rank": i,
            "username": u.username,
            "alliance_tag": alliance_by_user.get(u.id),
            "total_points": total,
        }
        for i, (u, total) in enumerate(scored[:limit], start=1)
    ]


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
    rankings = await _landing_rankings(db)
    return templates.TemplateResponse(
        name="install.html",
        request=request,
        context={
            "request": request,
            "rankings": rankings,
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
    return templates.TemplateResponse(
        name="login.html",
        request=request,
        context={"request": request, "code": code, "err": err, "ok": ok},
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
    return templates.TemplateResponse(
        name="signup.html",
        request=request,
        context={"request": request, "code": code, "err": err, "ok": ok},
    )


@router.post("/signup")
@limiter.limit("5/minute")
async def signup_submit(
    request: Request,
    db: DBSession,
    username: Annotated[str, Form(min_length=3, max_length=32)],
    email: Annotated[str, Form()],
    password: Annotated[str, Form(min_length=10)],
    code: str | None = None,
) -> Response:
    settings = get_settings()
    total = await _registered_count(db)
    if total >= settings.server_max_users:
        return RedirectResponse(
            f"/signup?err=Server+is+full+({total}/{settings.server_max_users}).+Try+another+server.",
            status_code=303,
        )

    # Reserved-username squat protection (mirrors /auth/register).
    admin = (settings.admin_username or "").strip()
    if admin and username.lower() == admin.lower():
        qs = f"&code={code}" if code else ""
        return RedirectResponse(
            f"/signup?err=That+username+is+reserved{qs}", status_code=303
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
        return templates.TemplateResponse(
            name="terminal_success.html",
            request=request,
            context={"request": request, "username": username},
        )

    resp = RedirectResponse("/dashboard", status_code=303)
    _set_auth_cookie(resp, token, request)
    return resp


@router.post("/signin")
@limiter.limit("10/minute")
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
        return RedirectResponse(f"/login?err=Wrong+username+or+password{qs}", status_code=303)

    token = create_access_token(user.id)

    if code:
        bound = await bind_token_to_code(db, code=code, token=token, user_id=user.id)
        if not bound:
            return RedirectResponse(
                "/login?err=Auth+code+invalid+or+expired.+Restart+sakusen+in+terminal.",
                status_code=303,
            )
        return templates.TemplateResponse(
            name="terminal_success.html",
            request=request,
            context={"request": request, "username": user.username},
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

    return templates.TemplateResponse(
        name="me.html",
        request=request,
        context={
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

    bld_res = await db.execute(select(Building).where(Building.planet_id == planet.id))
    levels_by_type: dict[str, int] = {b.building_type: b.level for b in bld_res.scalars().all()}

    def _bucket(types: tuple[BuildingType, ...]) -> list[dict]:
        rows = []
        for bt in types:
            rows.append(
                {
                    "key": bt.value,
                    "label": BUILDING_LABELS[bt],
                    "level": levels_by_type.get(bt.value, 0),
                }
            )
        return rows

    resources = _bucket(RESOURCE_BUILDINGS)
    facilities = _bucket(FACILITY_BUILDINGS)

    def_res = await db.execute(select(PlanetDefense).where(PlanetDefense.planet_id == planet.id))
    def_by_type: dict[str, int] = {d.defense_type: d.count for d in def_res.scalars().all()}
    defenses = [
        {
            "key": dt.value,
            "label": DEFENSE_LABELS[dt],
            "count": def_by_type.get(dt.value, 0),
        }
        for dt in DefenseType
    ]
    defense_total = sum(int(d["count"]) for d in defenses)
    built_count = sum(1 for r in resources + facilities if r["level"] > 0)

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

    return templates.TemplateResponse(
        name="dashboard.html",
        request=request,
        context={
            "request": request,
            "user": user,
            "current_planet": planet,
            "all_planets": planets,
            "production": report,
            "resources": resources,
            "facilities": facilities,
            "defenses": defenses,
            "defense_total": defense_total,
            "built_count": built_count,
            "active_queue": active_queue,
            "logs": logs,
            "unread": unread_count,
            "registered_count": registered_count,
            "online_count": online_count(),
            "server_name": settings.server_name,
            "server_max_users": settings.server_max_users,
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
        select(AllianceMember.user_id, Alliance.tag).join(
            Alliance, Alliance.id == AllianceMember.alliance_id
        )
    )
    alliance_by_user: dict[int, str] = {uid: tag for uid, tag in member_res.all()}

    scored: list[tuple[User, dict]] = []
    for u in users:
        pts = await user_points(db, u.id)
        scored.append((u, pts))
    scored.sort(key=lambda t: t[1]["total_points"], reverse=True)

    rows = []
    my_rank: int | None = None
    my_row: dict | None = None
    for i, (u, pts) in enumerate(scored, start=1):
        is_me = u.id == user.id
        row = {
            "rank": i,
            "user_id": u.id,
            "username": u.username,
            "alliance_tag": alliance_by_user.get(u.id),
            "is_me": is_me,
            **pts,
        }
        if is_me:
            my_rank = i
            my_row = row
        if i <= 100:
            rows.append(row)

    # Only carry my_row separately when I'm OUTSIDE the top 100. Template
    # appends it as a divider row at the bottom.
    tail_my_row = my_row if (my_rank is not None and my_rank > 100) else None

    return templates.TemplateResponse(
        name="leaderboard.html",
        request=request,
        context={
            "request": request,
            "rows": rows,
            "total_players": len(scored),
            "my_rank": my_rank,
            "my_points": (my_row or {}).get("total_points", 0),
            "tail_my_row": tail_my_row,
            "server_name": get_settings().server_name,
        },
    )


# ============================================================================
# /players
# ============================================================================
PLAYERS_PER_PAGE = 50


@router.get("/players", response_class=HTMLResponse)
async def players_page(
    request: Request,
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
    page: int = 1,
    q: str | None = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)

    # Filter by username substring if provided.
    base_q = select(User).where(User.current_universe_id == user.current_universe_id)
    if q:
        base_q = base_q.where(User.username.ilike(f"%{q}%"))

    total_res = await db.execute(select(func.count()).select_from(base_q.subquery()))
    total = int(total_res.scalar() or 0)

    page = max(1, page)
    offset = (page - 1) * PLAYERS_PER_PAGE
    res = await db.execute(base_q.order_by(User.username).offset(offset).limit(PLAYERS_PER_PAGE))
    players = list(res.scalars().all())

    # Alliance tag per user
    member_res = await db.execute(
        select(AllianceMember.user_id, Alliance.tag).join(
            Alliance, Alliance.id == AllianceMember.alliance_id
        )
    )
    alliance_by_user: dict[int, str] = {uid: tag for uid, tag in member_res.all()}

    rows = [
        {
            "id": p.id,
            "username": p.username,
            "alliance_tag": alliance_by_user.get(p.id),
            "is_me": p.id == user.id,
            "created_at": p.created_at,
        }
        for p in players
    ]
    pages = max(1, (total + PLAYERS_PER_PAGE - 1) // PLAYERS_PER_PAGE)

    return templates.TemplateResponse(
        name="players.html",
        request=request,
        context={
            "request": request,
            "rows": rows,
            "total": total,
            "page": page,
            "pages": pages,
            "q": q or "",
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
            select(func.count())
            .select_from(AllianceMember)
            .where(AllianceMember.alliance_id == a.id)
        )
        member_count = int(count_res.scalar() or 0)
        founder = await db.get(User, a.founder_id)
        is_member = my_alliance is not None and my_alliance.id == a.id
        alliances.append(
            {
                "id": a.id,
                "tag": a.tag,
                "name": a.name,
                "description": a.description,
                "member_count": member_count,
                "founder_username": founder.username if founder else "?",
                "is_member": is_member,
            }
        )

    return templates.TemplateResponse(
        name="alliances.html",
        request=request,
        context={
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

    existing_m = await db.execute(select(AllianceMember).where(AllianceMember.user_id == user.id))
    if existing_m.scalar_one_or_none() is not None:
        return RedirectResponse("/alliances?err=Leave+your+current+alliance+first", status_code=303)

    a = Alliance(
        tag=tag.upper(),
        name=name,
        description=description,
        founder_id=user.id,
    )
    db.add(a)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        return RedirectResponse("/alliances?err=Tag+or+name+already+taken", status_code=303)
    db.add(AllianceMember(alliance_id=a.id, user_id=user.id, role=AllianceRole.FOUNDER.value))
    await db.commit()
    return RedirectResponse(f"/alliances/{a.tag}", status_code=303)


@router.get("/alliances/{tag}", response_class=HTMLResponse)
async def alliance_detail_page(
    tag: str,
    request: Request,
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
    err: str | None = None,
    ok: str | None = None,
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
    is_founder = a.founder_id == user.id

    m_res = await db.execute(
        select(AllianceMember, User)
        .join(User, User.id == AllianceMember.user_id)
        .where(AllianceMember.alliance_id == a.id)
        .order_by(AllianceMember.joined_at)
    )
    members = []
    for m, u in m_res.all():
        pts = await user_points(db, u.id)
        members.append(
            {
                "user_id": u.id,
                "username": u.username,
                "role": m.role,
                "joined_at": m.joined_at,
                "is_me": u.id == user.id,
                "total_points": pts["total_points"],
            }
        )

    # Has the viewer already applied to THIS alliance?
    my_req_res = await db.execute(
        select(AllianceJoinRequest).where(
            AllianceJoinRequest.user_id == user.id,
            AllianceJoinRequest.alliance_id == a.id,
        )
    )
    my_pending_for_this = my_req_res.scalar_one_or_none() is not None

    # Founder-only: pending applicants.
    pending: list[dict] = []
    if is_founder:
        p_res = await db.execute(
            select(AllianceJoinRequest, User)
            .join(User, User.id == AllianceJoinRequest.user_id)
            .where(AllianceJoinRequest.alliance_id == a.id)
            .order_by(AllianceJoinRequest.created_at)
        )
        for r, u in p_res.all():
            pending.append(
                {
                    "username": u.username,
                    "message": r.message,
                    "created_at": r.created_at,
                }
            )

    return templates.TemplateResponse(
        name="alliance_detail.html",
        request=request,
        context={
            "request": request,
            "alliance": a,
            "members": members,
            "founder_username": founder.username if founder else "?",
            "my_alliance": my_alliance,
            "is_member": is_member,
            "is_founder": is_founder,
            "my_pending_for_this": my_pending_for_this,
            "pending": pending,
            "server_name": get_settings().server_name,
            "err": err,
            "ok": ok,
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

    existing_m = await db.execute(select(AllianceMember).where(AllianceMember.user_id == user.id))
    if existing_m.scalar_one_or_none() is not None:
        return RedirectResponse("/alliances?err=Leave+your+current+alliance+first", status_code=303)

    existing_r = await db.execute(
        select(AllianceJoinRequest).where(AllianceJoinRequest.user_id == user.id)
    )
    if existing_r.scalar_one_or_none() is not None:
        return RedirectResponse(
            "/alliances?err=You+already+have+a+pending+request+(withdraw+it+first)",
            status_code=303,
        )

    a_res = await db.execute(select(Alliance).where(Alliance.tag == tag.upper()))
    a = a_res.scalar_one_or_none()
    if a is None:
        return RedirectResponse("/alliances?err=Alliance+not+found", status_code=303)

    db.add(AllianceJoinRequest(alliance_id=a.id, user_id=user.id))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return RedirectResponse(f"/alliances/{a.tag}?err=Request+already+pending", status_code=303)
    return RedirectResponse(
        f"/alliances/{a.tag}?ok=Join+request+sent.+Wait+for+the+founder+to+approve.",
        status_code=303,
    )


@router.post("/alliances/{tag}/requests/{username}/approve")
async def alliance_request_approve_form(
    tag: str,
    username: str,
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)

    a_res = await db.execute(select(Alliance).where(Alliance.tag == tag.upper()))
    a = a_res.scalar_one_or_none()
    if a is None or a.founder_id != user.id:
        return RedirectResponse("/alliances?err=Not+authorized", status_code=303)

    u_res = await db.execute(select(User).where(User.username == username))
    applicant = u_res.scalar_one_or_none()
    if applicant is None:
        return RedirectResponse(f"/alliances/{a.tag}?err=User+not+found", status_code=303)

    r_res = await db.execute(
        select(AllianceJoinRequest).where(
            AllianceJoinRequest.alliance_id == a.id,
            AllianceJoinRequest.user_id == applicant.id,
        )
    )
    req = r_res.scalar_one_or_none()
    if req is None:
        return RedirectResponse(f"/alliances/{a.tag}?err=No+pending+request", status_code=303)

    # If applicant joined elsewhere meanwhile, drop the stale request.
    in_other = await db.execute(
        select(AllianceMember).where(AllianceMember.user_id == applicant.id)
    )
    if in_other.scalar_one_or_none() is not None:
        await db.delete(req)
        await db.commit()
        return RedirectResponse(
            f"/alliances/{a.tag}?err={username}+is+already+in+an+alliance",
            status_code=303,
        )

    db.add(AllianceMember(alliance_id=a.id, user_id=applicant.id, role=AllianceRole.MEMBER.value))
    await db.delete(req)
    await db.commit()
    return RedirectResponse(f"/alliances/{a.tag}?ok={username}+approved", status_code=303)


@router.post("/alliances/{tag}/requests/{username}/reject")
async def alliance_request_reject_form(
    tag: str,
    username: str,
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)
    a_res = await db.execute(select(Alliance).where(Alliance.tag == tag.upper()))
    a = a_res.scalar_one_or_none()
    if a is None or a.founder_id != user.id:
        return RedirectResponse("/alliances?err=Not+authorized", status_code=303)
    u_res = await db.execute(select(User).where(User.username == username))
    applicant = u_res.scalar_one_or_none()
    if applicant is None:
        return RedirectResponse(f"/alliances/{a.tag}?err=User+not+found", status_code=303)
    r_res = await db.execute(
        select(AllianceJoinRequest).where(
            AllianceJoinRequest.alliance_id == a.id,
            AllianceJoinRequest.user_id == applicant.id,
        )
    )
    req = r_res.scalar_one_or_none()
    if req is not None:
        await db.delete(req)
        await db.commit()
    return RedirectResponse(f"/alliances/{a.tag}?ok={username}+rejected", status_code=303)


@router.post("/alliances/withdraw-request")
async def alliance_request_withdraw_form(
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)
    res = await db.execute(
        select(AllianceJoinRequest).where(AllianceJoinRequest.user_id == user.id)
    )
    req = res.scalar_one_or_none()
    if req is not None:
        await db.delete(req)
        await db.commit()
    return RedirectResponse("/alliances?ok=Request+withdrawn", status_code=303)


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
        select(func.count()).select_from(AllianceMember).where(AllianceMember.alliance_id == a.id)
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
