"""Admin web panel (cookie-based, admin_username only).

Routes:
    GET  /admin                                    -> dashboard
    GET  /admin/user/{user_id}                     -> user edit page
    POST /admin/user/{user_id}/researches          -> save tech levels
    POST /admin/user/{user_id}/planet/new          -> create planet
    GET  /admin/user/{user_id}/planet/{planet_id}  -> planet edit page
    POST /admin/user/{user_id}/planet/{planet_id}  -> save planet
    POST /admin/user/{user_id}/planet/{planet_id}/delete
    POST /admin/universe/speed-form                -> set universe speed

All HTML is rendered from backend/app/templates/admin/.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.web import COOKIE_NAME, _user_from_cookie
from backend.app.config import get_settings
from backend.app.deps import DBSession
from backend.app.game.colonization import generate_planet_attributes
from backend.app.game.constants import (
    BUILDING_LABELS,
    DEFENSE_LABELS,
    SHIP_LABELS,
    TECH_LABELS,
    BuildingType,
    DefenseType,
    ShipType,
    TechType,
)
from backend.app.models.building import Building
from backend.app.models.planet import Planet
from backend.app.models.research import Research
from backend.app.models.ship import PlanetDefense, PlanetShip
from backend.app.models.user import User
from backend.app.services.planet_code import generate_unique_code
from backend.app.services.resource_service import refresh_planet_resources
from backend.app.services.universe_service import get_default_universe
from backend.app.web_templates import templates

router = APIRouter(tags=["admin-ui"])


async def _require_admin_or_redirect(token: str | None, db: AsyncSession) -> User | Response:
    settings = get_settings()
    admin = (settings.admin_username or "").strip()
    if not admin:
        return RedirectResponse("/login?err=Admin+disabled", status_code=302)
    user = await _user_from_cookie(token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)
    if user.username != admin:
        return _forbidden(user.username, admin)
    return user


def _forbidden(your_user: str, admin: str) -> HTMLResponse:
    # Render the forbidden template inline (no request object needed since
    # we're not setting any cookies here).
    # Minimal request-like dict for template
    return HTMLResponse(
        templates.get_template("admin/forbidden.html").render(
            request=None,
            your_user=your_user,
            admin=admin,
        ),
        status_code=403,
    )


# ============================================================================
# Dashboard
# ============================================================================
@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: DBSession,
    tarmy_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    auth = await _require_admin_or_redirect(tarmy_token, db)
    if isinstance(auth, Response):
        return auth
    admin_user = auth

    users_res = await db.execute(select(User).order_by(User.id))
    users = list(users_res.scalars().all())
    user_rows = []
    for u in users:
        planet_res = await db.execute(
            select(func.count()).select_from(Planet).where(Planet.owner_user_id == u.id)
        )
        planet_count = int(planet_res.scalar() or 0)
        user_rows.append(
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "planet_count": planet_count,
            }
        )

    universe = await get_default_universe(db)

    return templates.TemplateResponse(
        name="admin/index.html",
        request=request,
        context={
            "request": request,
            "admin_user": admin_user,
            "users": user_rows,
            "universe": universe,
        },
    )


@router.post("/admin/universe/speed-form")
async def admin_set_speed_form(
    db: DBSession,
    speed: Annotated[int, Form(ge=1, le=100)],
    tarmy_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    auth = await _require_admin_or_redirect(tarmy_token, db)
    if isinstance(auth, Response):
        return auth
    universe = await get_default_universe(db)
    if universe is not None:
        # Refresh every planet at the OLD speed before flipping; otherwise
        # lag windows would retroactively apply the new rate.
        planet_ids = list(
            (await db.execute(select(Planet.id).where(Planet.universe_id == universe.id)))
            .scalars()
            .all()
        )
        for pid in planet_ids:
            await refresh_planet_resources(db, pid)
        universe.speed_economy = speed
        universe.speed_fleet = speed
        universe.speed_research = speed
        await db.commit()
    return RedirectResponse("/admin", status_code=303)


# ============================================================================
# User edit
# ============================================================================
@router.get("/admin/user/{user_id}", response_class=HTMLResponse)
async def admin_user_edit(
    user_id: int,
    request: Request,
    db: DBSession,
    tarmy_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    auth = await _require_admin_or_redirect(tarmy_token, db)
    if isinstance(auth, Response):
        return auth

    target = await db.get(User, user_id)
    if target is None:
        return HTMLResponse("user not found", status_code=404)

    tech_res = await db.execute(select(Research).where(Research.user_id == user_id))
    techs = {r.tech_type: r.level for r in tech_res.scalars().all()}
    tech_fields = [
        {"key": tt.value, "label": TECH_LABELS[tt], "level": techs.get(tt.value, 0)}
        for tt in TechType
    ]

    planet_res = await db.execute(
        select(Planet).where(Planet.owner_user_id == user_id).order_by(Planet.id)
    )
    planets = list(planet_res.scalars().all())

    return templates.TemplateResponse(
        name="admin/user.html",
        request=request,
        context={
            "request": request,
            "target": target,
            "tech_fields": tech_fields,
            "planets": planets,
        },
    )


@router.post("/admin/user/{user_id}/researches")
async def admin_save_researches(
    user_id: int,
    request: Request,
    db: DBSession,
    tarmy_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    auth = await _require_admin_or_redirect(tarmy_token, db)
    if isinstance(auth, Response):
        return auth

    form = await request.form()
    for tt in TechType:
        key = f"tech_{tt.value}"
        if key not in form:
            continue
        try:
            new_level = max(0, int(str(form[key])))
        except ValueError:
            continue
        res = await db.execute(
            select(Research).where(Research.user_id == user_id, Research.tech_type == tt.value)
        )
        row = res.scalar_one_or_none()
        if row is None:
            db.add(Research(user_id=user_id, tech_type=tt.value, level=new_level))
        else:
            row.level = new_level
    await db.commit()
    return RedirectResponse(f"/admin/user/{user_id}", status_code=303)


@router.post("/admin/user/{user_id}/planet/new")
async def admin_create_planet(
    user_id: int,
    db: DBSession,
    galaxy: Annotated[int, Form(ge=1, le=9)],
    system: Annotated[int, Form(ge=1, le=499)],
    position: Annotated[int, Form(ge=1, le=15)],
    name: Annotated[str, Form(min_length=1, max_length=32)] = "Colony",
    tarmy_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    auth = await _require_admin_or_redirect(tarmy_token, db)
    if isinstance(auth, Response):
        return auth

    target = await db.get(User, user_id)
    if target is None:
        return HTMLResponse("user not found", status_code=404)

    existing = await db.execute(
        select(Planet).where(
            Planet.universe_id == target.current_universe_id,
            Planet.galaxy == galaxy,
            Planet.system == system,
            Planet.position == position,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return RedirectResponse(f"/admin/user/{user_id}?err=slot+taken", status_code=303)

    attrs = generate_planet_attributes(position, random.Random())
    code = await generate_unique_code(db)
    planet = Planet(
        owner_user_id=user_id,
        universe_id=target.current_universe_id,
        galaxy=galaxy,
        system=system,
        position=position,
        code=code,
        name=name,
        fields_used=0,
        fields_total=attrs.fields_total,
        temp_min=attrs.temp_min,
        temp_max=attrs.temp_max,
        resources_metal=500.0,
        resources_crystal=500.0,
        resources_deuterium=0.0,
        resources_last_updated_at=datetime.now(UTC),
    )
    db.add(planet)
    await db.flush()
    for bt in BuildingType:
        db.add(Building(planet_id=planet.id, building_type=bt.value, level=0))
    await db.commit()
    return RedirectResponse(f"/admin/user/{user_id}/planet/{planet.id}", status_code=303)


# ============================================================================
# Planet edit
# ============================================================================
@router.get("/admin/user/{user_id}/planet/{planet_id}", response_class=HTMLResponse)
async def admin_planet_edit(
    user_id: int,
    planet_id: int,
    request: Request,
    db: DBSession,
    tarmy_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    auth = await _require_admin_or_redirect(tarmy_token, db)
    if isinstance(auth, Response):
        return auth

    planet = await db.get(Planet, planet_id)
    if planet is None or planet.owner_user_id != user_id:
        return HTMLResponse("planet not found", status_code=404)
    target = await db.get(User, user_id)

    bld_res = await db.execute(select(Building).where(Building.planet_id == planet_id))
    bld_map = {b.building_type: b.level for b in bld_res.scalars().all()}
    building_fields = [
        {"key": bt.value, "label": BUILDING_LABELS[bt], "level": bld_map.get(bt.value, 0)}
        for bt in BuildingType
    ]

    ship_res = await db.execute(select(PlanetShip).where(PlanetShip.planet_id == planet_id))
    ship_map = {s.ship_type: s.count for s in ship_res.scalars().all()}
    ship_fields = [
        {"key": st.value, "label": SHIP_LABELS[st], "count": ship_map.get(st.value, 0)}
        for st in ShipType
    ]

    def_res = await db.execute(select(PlanetDefense).where(PlanetDefense.planet_id == planet_id))
    def_map = {d.defense_type: d.count for d in def_res.scalars().all()}
    defense_fields = [
        {"key": dt.value, "label": DEFENSE_LABELS[dt], "count": def_map.get(dt.value, 0)}
        for dt in DefenseType
    ]

    return templates.TemplateResponse(
        name="admin/planet.html",
        request=request,
        context={
            "request": request,
            "planet": planet,
            "target": target,
            "building_fields": building_fields,
            "ship_fields": ship_fields,
            "defense_fields": defense_fields,
        },
    )


@router.post("/admin/user/{user_id}/planet/{planet_id}")
async def admin_save_planet(
    user_id: int,
    planet_id: int,
    request: Request,
    db: DBSession,
    tarmy_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    auth = await _require_admin_or_redirect(tarmy_token, db)
    if isinstance(auth, Response):
        return auth

    planet = await db.get(Planet, planet_id)
    if planet is None or planet.owner_user_id != user_id:
        return HTMLResponse("planet not found", status_code=404)

    form = await request.form()
    if name := form.get("name"):
        planet.name = str(name)[:32]
    for fld in ("fields_used", "fields_total", "temp_min", "temp_max"):
        if fld in form:
            try:
                setattr(planet, fld, int(str(form[fld])))
            except ValueError:
                pass
    for src, dst in (
        ("metal", "resources_metal"),
        ("crystal", "resources_crystal"),
        ("deuterium", "resources_deuterium"),
    ):
        if src in form:
            try:
                setattr(planet, dst, float(max(0, int(str(form[src])))))
            except ValueError:
                pass
    planet.resources_last_updated_at = datetime.now(UTC)

    for bt in BuildingType:
        key = f"bld_{bt.value}"
        if key not in form:
            continue
        try:
            lvl = max(0, int(str(form[key])))
        except ValueError:
            continue
        bld_res = await db.execute(
            select(Building).where(
                Building.planet_id == planet_id, Building.building_type == bt.value
            )
        )
        bld_row = bld_res.scalar_one_or_none()
        if bld_row is None:
            db.add(Building(planet_id=planet_id, building_type=bt.value, level=lvl))
        else:
            bld_row.level = lvl

    for st in ShipType:
        key = f"ship_{st.value}"
        if key not in form:
            continue
        try:
            cnt = max(0, int(str(form[key])))
        except ValueError:
            continue
        ship_res = await db.execute(
            select(PlanetShip).where(
                PlanetShip.planet_id == planet_id, PlanetShip.ship_type == st.value
            )
        )
        ship_row = ship_res.scalar_one_or_none()
        if ship_row is None:
            if cnt > 0:
                db.add(PlanetShip(planet_id=planet_id, ship_type=st.value, count=cnt))
        else:
            ship_row.count = cnt

    for dt in DefenseType:
        key = f"def_{dt.value}"
        if key not in form:
            continue
        try:
            cnt = max(0, int(str(form[key])))
        except ValueError:
            continue
        def_res = await db.execute(
            select(PlanetDefense).where(
                PlanetDefense.planet_id == planet_id,
                PlanetDefense.defense_type == dt.value,
            )
        )
        def_row = def_res.scalar_one_or_none()
        if def_row is None:
            if cnt > 0:
                db.add(PlanetDefense(planet_id=planet_id, defense_type=dt.value, count=cnt))
        else:
            def_row.count = cnt

    await db.commit()
    return RedirectResponse(f"/admin/user/{user_id}/planet/{planet_id}", status_code=303)


@router.post("/admin/user/{user_id}/planet/{planet_id}/delete")
async def admin_delete_planet(
    user_id: int,
    planet_id: int,
    db: DBSession,
    tarmy_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    auth = await _require_admin_or_redirect(tarmy_token, db)
    if isinstance(auth, Response):
        return auth

    planet = await db.get(Planet, planet_id)
    if planet is None or planet.owner_user_id != user_id:
        return HTMLResponse("planet not found", status_code=404)
    await db.delete(planet)
    await db.commit()
    return RedirectResponse(f"/admin/user/{user_id}", status_code=303)
