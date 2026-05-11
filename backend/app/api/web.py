"""Web UI: login page + dashboard.

Routes:
    GET  /              -> redirect to /dashboard (if signed in) or /login
    GET  /login         -> login + signup form
    POST /signup        -> create user; if ?code= bind to CLI device flow,
                           else set cookie + redirect to /dashboard
    POST /signin        -> sign in; same dual behavior
    GET  /dashboard     -> server-rendered status: planet, resources, queue, logs
    GET  /logout        -> clear cookie + redirect to /login

Plus legacy /signup GET kept as alias for /login.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Cookie, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.device import bind_token_to_code
from backend.app.config import get_settings
from backend.app.deps import DBSession
from backend.app.game.constants import BUILDING_LABELS, BuildingType
from backend.app.models.building import Building
from backend.app.models.message import Message
from backend.app.models.planet import Planet
from backend.app.models.queue import BuildQueue
from backend.app.models.user import User
from backend.app.security import create_access_token, decode_token, hash_password, verify_password
from backend.app.services.resource_service import refresh_planet_resources
from backend.app.services.universe_service import (
    assign_starting_planet,
    ensure_default_universe,
    ensure_user_researches,
)

router = APIRouter(tags=["web"])

COOKIE_NAME = "ogame_token"


# ============================================================================
# CSS
# ============================================================================
_PAGE_CSS = """
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    background: #000;
    color: #d4d4d4;
    font-family: 'SF Mono', 'JetBrains Mono', Menlo, Monaco, 'Courier New', monospace;
    margin: 0;
    line-height: 1.5;
    font-size: 14px;
    background-image:
      radial-gradient(at 10% 10%, rgba(251, 191, 36, 0.04), transparent 40%),
      radial-gradient(at 90% 90%, rgba(132, 204, 22, 0.03), transparent 40%);
  }
  a { color: #fbbf24; text-decoration: none; }
  a:hover { color: #fde68a; }
  code { color: #fbbf24; background: #171717; padding: 0 0.25rem; }

  /* Layout */
  .login-shell {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem 1rem;
  }
  .login-container { width: 100%; max-width: 520px; }
  .dash-shell {
    max-width: 1200px;
    margin: 0 auto;
    padding: 1.5rem;
  }

  /* Logo */
  .logo {
    color: #fbbf24;
    text-align: center;
    line-height: 1.2;
    white-space: pre;
    font-size: 0.9rem;
    margin: 0 0 0.6rem;
  }
  .tagline {
    text-align: center;
    color: #525252;
    font-size: 0.75rem;
    letter-spacing: 0.25em;
    text-transform: uppercase;
    margin: 0 0 2.5rem;
  }

  /* Card */
  .card {
    background: #0a0a0a;
    border: 1px solid #1f1f1f;
    padding: 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 0 0 1px rgba(251, 191, 36, 0.03);
  }
  .card:focus-within { border-color: #2a2a2a; }
  .card-title {
    color: #fbbf24;
    font-size: 0.7rem;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    margin: 0 0 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #1f1f1f;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .card-title small { color: #525252; font-weight: normal; letter-spacing: 0.1em; }

  /* Form */
  .field {
    display: block;
    margin-bottom: 0.9rem;
  }
  .field-label {
    display: block;
    color: #737373;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    margin-bottom: 0.35rem;
  }
  input[type=text], input[type=email], input[type=password] {
    display: block;
    width: 100%;
    background: #000;
    color: #fafafa;
    border: 1px solid #262626;
    padding: 0.65rem 0.85rem;
    font-family: inherit;
    font-size: 0.95rem;
    transition: border-color 0.15s, background 0.15s;
  }
  input:focus {
    outline: none;
    border-color: #fbbf24;
    background: #0a0a0a;
  }
  button {
    display: block;
    width: 100%;
    background: transparent;
    color: #fbbf24;
    border: 1px solid #fbbf24;
    padding: 0.75rem 1rem;
    font-family: inherit;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    cursor: pointer;
    transition: all 0.15s;
    margin-top: 0.5rem;
  }
  button:hover {
    background: #fbbf24;
    color: #000;
  }
  button.ghost {
    color: #737373;
    border-color: #262626;
  }
  button.ghost:hover {
    color: #d4d4d4;
    border-color: #525252;
    background: #0a0a0a;
  }

  .err {
    color: #ef4444;
    border-left: 2px solid #ef4444;
    padding: 0.6rem 0.8rem;
    margin: 0 0 1rem;
    background: #1f0a0a;
    font-size: 0.85rem;
  }
  .ok { color: #84cc16; }
  .ok-banner {
    color: #84cc16;
    border-left: 2px solid #84cc16;
    padding: 0.6rem 0.8rem;
    margin: 0 0 1rem;
    background: #0a1f0a;
    font-size: 0.85rem;
  }
  .info-banner {
    background: #0a0a0a;
    border-left: 2px solid #fbbf24;
    border-top: 1px solid #1f1f1f;
    border-right: 1px solid #1f1f1f;
    border-bottom: 1px solid #1f1f1f;
    padding: 0.8rem 1rem;
    margin: 0 0 1.5rem;
    font-size: 0.85rem;
  }
  .info-banner strong { color: #fbbf24; }

  .hint { color: #525252; font-size: 0.75rem; margin: 0.5rem 0 0; }

  .key {
    display: block;
    background: #000;
    color: #fbbf24;
    border: 1px dashed #404040;
    padding: 1rem;
    font-size: 0.75rem;
    word-break: break-all;
    user-select: all;
    margin: 0.5rem 0;
  }

  /* Dashboard */
  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 1px solid #1f1f1f;
    padding-bottom: 0.8rem;
    margin-bottom: 1.5rem;
  }
  .topbar-left {
    display: flex;
    align-items: baseline;
    gap: 0.8rem;
  }
  .topbar-brand {
    color: #fbbf24;
    font-weight: 700;
    letter-spacing: 0.15em;
    font-size: 0.85rem;
  }
  .topbar-user { color: #d4d4d4; font-size: 0.85rem; }
  .topbar-user b { color: #fbbf24; }
  .topbar-right { font-size: 0.8rem; color: #737373; }
  .topbar-right a { margin-left: 1rem; }

  .planet-tabs {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin: 0 0 1rem;
  }
  .planet-tab {
    background: #0a0a0a;
    border: 1px solid #262626;
    padding: 0.4rem 0.8rem;
    color: #a3a3a3;
    font-size: 0.8rem;
    text-decoration: none;
    transition: all 0.15s;
  }
  .planet-tab:hover { border-color: #525252; color: #d4d4d4; }
  .planet-tab.active {
    border-color: #fbbf24;
    color: #fbbf24;
    background: #1a140a;
  }

  .grid-3 {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin-bottom: 1rem;
  }
  .grid-2 {
    display: grid;
    grid-template-columns: 3fr 2fr;
    gap: 1rem;
  }
  @media (max-width: 800px) {
    .grid-3, .grid-2 { grid-template-columns: 1fr; }
  }

  .metric { margin-bottom: 0.55rem; }
  .metric-label {
    color: #737373;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  .metric-value {
    font-size: 1.05rem;
    color: #fafafa;
  }
  .metric-value.metal { color: #facc15; }
  .metric-value.crystal { color: #67e8f9; }
  .metric-value.deut { color: #c084fc; }
  .metric-value.pos { color: #84cc16; }
  .metric-value.neg { color: #ef4444; }
  .metric-sub {
    color: #525252;
    font-size: 0.75rem;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
  }
  th {
    text-align: left;
    color: #737373;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 0.4rem 0.5rem;
    border-bottom: 1px solid #1f1f1f;
    font-weight: normal;
  }
  td {
    padding: 0.4rem 0.5rem;
    border-bottom: 1px solid #0f0f0f;
    color: #d4d4d4;
  }
  tr:last-child td { border-bottom: none; }
  td.right { text-align: right; }
  td.dim { color: #737373; }
  td.success { color: #84cc16; }
  td.muted { color: #525252; font-style: italic; }

  .empty-state {
    color: #525252;
    text-align: center;
    padding: 1.5rem 0;
    font-style: italic;
    font-size: 0.85rem;
  }
"""


_LOGO_BANNER = """  ███████╗██████╗  █████╗  ██████╗███████╗     ██████╗  █████╗ ██╗      █████╗  ██████╗████████╗██╗ ██████╗
  ██╔════╝██╔══██╗██╔══██╗██╔════╝██╔════╝    ██╔════╝ ██╔══██╗██║     ██╔══██╗██╔════╝╚══██╔══╝██║██╔════╝
  ███████╗██████╔╝███████║██║     █████╗      ██║  ███╗███████║██║     ███████║██║        ██║   ██║██║
  ╚════██║██╔═══╝ ██╔══██║██║     ██╔══╝      ██║   ██║██╔══██║██║     ██╔══██║██║        ██║   ██║██║
  ███████║██║     ██║  ██║╚██████╗███████╗    ╚██████╔╝██║  ██║███████╗██║  ██║╚██████╗   ██║   ██║╚██████╗
  ╚══════╝╚═╝     ╚═╝  ╚═╝ ╚═════╝╚══════╝     ╚═════╝ ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝ ╚═════╝   ╚═╝   ╚═╝ ╚═════╝"""


def _shell(title: str, body: str, with_login_layout: bool = False) -> str:
    layout_class = "login-shell" if with_login_layout else "dash-shell"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>{title}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
<div class="{layout_class}">
{body}
</div>
</body>
</html>"""


# ============================================================================
# Helpers
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


def _set_auth_cookie(resp: Response, token: str) -> None:
    settings = get_settings()
    # Bump to at least 30 days even if JWT_EXPIRE_MINUTES is shorter, so
    # the browser keeps the cookie even when JWT is still valid via its
    # own exp claim. Hard cap at JWT expiry.
    max_age_sec = max(30 * 24 * 3600, settings.jwt_expire_minutes * 60)
    resp.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=max_age_sec,
        expires=max_age_sec,           # legacy header for older browsers
        httponly=True,
        samesite="lax",
        secure=False,                  # explicit: works over plain HTTP
        path="/",
    )


def _fmt_int(v: float | int) -> str:
    n = int(v)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 10_000:
        return f"{n / 1_000:.1f}k"
    return f"{n:,}"


def _local_hhmmss(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%H:%M:%S")


def _remaining_str(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = (dt - datetime.now(timezone.utc)).total_seconds()
    if delta < 0:
        return "done"
    s = int(delta)
    if s < 60:
        return f"{s}s"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}m{sec:02d}s"
    h, rem = divmod(s, 3600)
    m, _ = divmod(rem, 60)
    return f"{h}h{m:02d}m"


# ============================================================================
# Routes: login / signup / signin / logout
# ============================================================================
@router.get("/", response_class=HTMLResponse)
async def root(
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is not None:
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    db: DBSession,
    code: str | None = None,
    err: str | None = None,
    ok: str | None = None,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    # Skip page if already signed in (unless device flow with code)
    if not code:
        user = await _user_from_cookie(ogame_token, db)
        if user is not None:
            return RedirectResponse("/dashboard", status_code=302)

    banner = ""
    if code:
        banner = (
            f'<div class="info-banner">'
            f'<strong>Terminal authentication</strong> &middot; '
            f'sign in below to authorize your <code>ogame</code> terminal session. '
            f'When you finish, return to the terminal.'
            f"</div>"
        )
    err_html = f'<div class="err">{err}</div>' if err else ""
    ok_html = f'<div class="ok-banner">{ok}</div>' if ok else ""

    qs = f"?code={code}" if code else ""
    body = f"""
<div class="login-container">
<pre class="logo">{_LOGO_BANNER}</pre>
<p class="tagline">terminal-based · ogame clone</p>

{banner}
{err_html}
{ok_html}

<div class="card">
  <h2 class="card-title">Sign in <small>existing account</small></h2>
  <form action="/signin{qs}" method="post" autocomplete="on">
    <label class="field">
      <span class="field-label">Username</span>
      <input type="text" name="username" required autocomplete="username">
    </label>
    <label class="field">
      <span class="field-label">Password</span>
      <input type="password" name="password" required autocomplete="current-password">
    </label>
    <button type="submit">Enter</button>
  </form>
</div>

<div class="card">
  <h2 class="card-title">New account <small>create commander</small></h2>
  <form action="/signup{qs}" method="post" autocomplete="on">
    <label class="field">
      <span class="field-label">Username</span>
      <input type="text" name="username" minlength="3" maxlength="32" required autocomplete="username">
    </label>
    <label class="field">
      <span class="field-label">Email</span>
      <input type="email" name="email" required autocomplete="email">
    </label>
    <label class="field">
      <span class="field-label">Password (6+ chars)</span>
      <input type="password" name="password" minlength="6" required autocomplete="new-password">
    </label>
    <button type="submit" class="ghost">Sign up</button>
  </form>
  <p class="hint">A homeworld will be assigned automatically at registration.</p>
</div>
</div>
"""
    return HTMLResponse(_shell("Sign in &middot; Space Galactic", body, with_login_layout=True))


@router.get("/signup", response_class=HTMLResponse)
async def signup_alias(
    db: DBSession,
    code: str | None = None,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    """Backward-compatible alias of /login (used by CLI device flow URL)."""
    return await login_page(db, code=code, ogame_token=ogame_token)


@router.post("/signup")
async def signup_submit(
    db: DBSession,
    username: Annotated[str, Form(min_length=3, max_length=32)],
    email: Annotated[str, Form()],
    password: Annotated[str, Form(min_length=6)],
    code: str | None = None,
) -> Response:
    existing = await db.execute(
        select(User).where(or_(User.username == username, User.email == email))
    )
    if existing.scalar_one_or_none() is not None:
        return RedirectResponse(
            f"/login?err=That+username+or+email+is+already+taken{('&code=' + code) if code else ''}",
            status_code=303,
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
                "/login?err=Auth+code+invalid+or+expired.+Restart+ogame+in+terminal.",
                status_code=303,
            )
        return await _terminal_success_page(username)

    resp = RedirectResponse("/dashboard", status_code=303)
    _set_auth_cookie(resp, token)
    return resp


@router.post("/signin")
async def signin_submit(
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
                "/login?err=Auth+code+invalid+or+expired.+Restart+ogame+in+terminal.",
                status_code=303,
            )
        return await _terminal_success_page(username)

    resp = RedirectResponse("/dashboard", status_code=303)
    _set_auth_cookie(resp, token)
    return resp


@router.get("/logout")
async def logout() -> Response:
    resp = RedirectResponse("/login?ok=Signed+out", status_code=303)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


async def _terminal_success_page(username: str) -> HTMLResponse:
    body = f"""
<div class="login-container">
<pre class="logo">{_LOGO_BANNER}</pre>
<p class="tagline">terminal authentication</p>

<div class="card">
  <h2 class="card-title">Success <small>welcome, {username}</small></h2>
  <div class="ok-banner">
    Your <code>ogame</code> terminal session is now authenticated.
  </div>
  <p class="hint">
    Return to your terminal — the CLI is polling and will pick up your session in a couple of seconds.
    You can close this tab.
  </p>
</div>
</div>
"""
    return HTMLResponse(_shell("Signed in &middot; Space Galactic", body, with_login_layout=True))


# ============================================================================
# Dashboard
# ============================================================================
@router.get("/me", response_class=HTMLResponse)
async def me_page(
    db: DBSession,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Response:
    """Account info page (works while signed in)."""
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)

    planet_res = await db.execute(
        select(Planet).where(Planet.owner_user_id == user.id).order_by(Planet.id)
    )
    planets = list(planet_res.scalars().all())

    settings = get_settings()
    is_admin = (settings.admin_username or "") == user.username

    planets_rows = ""
    if planets:
        for p in planets:
            planets_rows += (
                f'<tr>'
                f'<td>#{p.id}</td>'
                f'<td><b>{p.name}</b></td>'
                f'<td class="dim">{p.galaxy}:{p.system}:{p.position}</td>'
                f'<td class="right">{p.fields_used}/{p.fields_total}</td>'
                f'<td class="right metric-value metal">{_fmt_int(p.resources_metal)}</td>'
                f'<td class="right metric-value crystal">{_fmt_int(p.resources_crystal)}</td>'
                f'<td class="right metric-value deut">{_fmt_int(p.resources_deuterium)}</td>'
                f'<td><a href="/dashboard?planet_id={p.id}">open</a></td>'
                f'</tr>'
            )
    else:
        planets_rows = '<tr><td colspan="8" class="empty-state">no planets</td></tr>'

    admin_link = (
        '<a href="/admin" style="margin-left:1rem;">admin panel</a>'
        if is_admin else ""
    )

    body = f"""
<div class="topbar">
  <div class="topbar-left">
    <span class="topbar-brand">SPACE GALACTIC</span>
    <span class="topbar-user">account</span>
  </div>
  <div class="topbar-right">
    <a href="/dashboard">dashboard</a>{admin_link}
    <a href="/logout" style="margin-left:1rem;">logout</a>
  </div>
</div>

<div class="card">
  <h2 class="card-title">Profile <small>commander</small></h2>
  <div class="grid-3">
    <div>
      <div class="metric-label">Username</div>
      <div class="metric-value"><b>{user.username}</b></div>
    </div>
    <div>
      <div class="metric-label">Email</div>
      <div class="metric-value">{user.email}</div>
    </div>
    <div>
      <div class="metric-label">Joined</div>
      <div class="metric-value">{user.created_at.strftime("%Y-%m-%d") if user.created_at else "?"}</div>
    </div>
  </div>
</div>

<div class="card">
  <h2 class="card-title">Planets <small>{len(planets)} owned</small></h2>
  <table>
    <thead>
      <tr>
        <th>id</th><th>name</th><th>coord</th>
        <th class="right">fields</th>
        <th class="right">metal</th>
        <th class="right">crystal</th>
        <th class="right">deut</th>
        <th></th>
      </tr>
    </thead>
    <tbody>{planets_rows}</tbody>
  </table>
</div>
"""
    return HTMLResponse(_shell("Account &middot; Space Galactic", body))


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    db: DBSession,
    request: Request,
    ogame_token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
    planet_id: int | None = None,
) -> Response:
    user = await _user_from_cookie(ogame_token, db)
    if user is None:
        return RedirectResponse("/login", status_code=302)

    # Planets owned
    planet_res = await db.execute(
        select(Planet).where(Planet.owner_user_id == user.id).order_by(Planet.id)
    )
    planets = list(planet_res.scalars().all())
    if not planets:
        body = f"""
<div class="topbar">
  <div class="topbar-left">
    <span class="topbar-brand">SPACE GALACTIC</span>
    <span class="topbar-user">commander <b>{user.username}</b></span>
  </div>
  <div class="topbar-right">
    <a href="/logout">logout</a>
  </div>
</div>
<div class="card">
  <h2 class="card-title">No planets</h2>
  <p>You have no planets yet. Contact the operator.</p>
</div>
"""
        return HTMLResponse(_shell("Dashboard &middot; Space Galactic", body))

    # Select planet (default = first; honor ?planet_id=)
    selected = planets[0]
    if planet_id is not None:
        for p in planets:
            if p.id == planet_id:
                selected = p
                break

    # Refresh resources
    planet, report = await refresh_planet_resources(db, selected.id)
    await db.commit()
    await db.refresh(planet)

    # Building counts (for fields, used)
    bld_res = await db.execute(
        select(Building).where(Building.planet_id == planet.id)
    )
    buildings = list(bld_res.scalars().all())

    # Active queue
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

    # Recent activity (applied queue)
    logs_res = await db.execute(
        select(BuildQueue)
        .where(BuildQueue.planet_id == planet.id, BuildQueue.applied.is_(True))
        .order_by(desc(BuildQueue.finished_at))
        .limit(15)
    )
    logs = list(logs_res.scalars().all())

    # Unread messages
    unread_res = await db.execute(
        select(func.count())
        .select_from(Message)
        .where(and_(Message.recipient_id == user.id, Message.read.is_(False)))
    )
    unread_count = int(unread_res.scalar() or 0)

    return HTMLResponse(_shell(
        "Dashboard &middot; Space Galactic",
        _render_dashboard(
            user=user,
            current_planet=planet,
            all_planets=planets,
            production=report,
            buildings=buildings,
            active_queue=active_queue,
            logs=logs,
            unread_count=unread_count,
        ),
    ))


# ============================================================================
# Dashboard renderers
# ============================================================================
def _render_dashboard(
    user: User,
    current_planet: Planet,
    all_planets: list[Planet],
    production,
    buildings: list[Building],
    active_queue: list[BuildQueue],
    logs: list[BuildQueue],
    unread_count: int,
) -> str:
    return (
        _render_topbar(user, unread_count)
        + _render_planet_tabs(all_planets, current_planet)
        + _render_planet_summary(current_planet, production)
        + _render_main_grid(current_planet, production, buildings, active_queue, logs)
    )


def _render_topbar(user: User, unread: int) -> str:
    msg = (
        f'<span class="ok">✉ {unread} new</span>'
        if unread > 0
        else '<span style="color:#525252">✉ inbox</span>'
    )
    settings = get_settings()
    is_admin = (settings.admin_username or "") == user.username
    admin_link = '<a href="/admin">admin</a>' if is_admin else ""
    return f"""
<meta http-equiv="refresh" content="10">
<div class="topbar">
  <div class="topbar-left">
    <span class="topbar-brand">SPACE GALACTIC</span>
    <span class="topbar-user">commander <b>{user.username}</b></span>
  </div>
  <div class="topbar-right">
    {msg}
    <a href="/dashboard">refresh</a>
    <a href="/me">account</a>
    {admin_link}
    <a href="/logout">logout</a>
  </div>
</div>
"""


def _render_planet_tabs(planets: list[Planet], current: Planet) -> str:
    tabs = []
    for p in planets:
        active = "active" if p.id == current.id else ""
        tabs.append(
            f'<a href="/dashboard?planet_id={p.id}" class="planet-tab {active}">'
            f'{p.name} <small style="color:#525252">{p.galaxy}:{p.system}:{p.position}</small>'
            f'</a>'
        )
    return f'<div class="planet-tabs">{"".join(tabs)}</div>'


def _render_planet_summary(planet: Planet, production) -> str:
    return f"""
<div class="card">
  <h2 class="card-title">
    {planet.name} <small>{planet.galaxy}:{planet.system}:{planet.position}</small>
  </h2>
  <div class="grid-3">
    <div>
      <div class="metric">
        <div class="metric-label">Metal</div>
        <div class="metric-value metal">{_fmt_int(planet.resources_metal)}</div>
        <div class="metric-sub">+{production.metal_per_hour:.0f}/h</div>
      </div>
      <div class="metric">
        <div class="metric-label">Crystal</div>
        <div class="metric-value crystal">{_fmt_int(planet.resources_crystal)}</div>
        <div class="metric-sub">+{production.crystal_per_hour:.0f}/h</div>
      </div>
      <div class="metric">
        <div class="metric-label">Deuterium</div>
        <div class="metric-value deut">{_fmt_int(planet.resources_deuterium)}</div>
        <div class="metric-sub">+{production.deuterium_per_hour:.0f}/h</div>
      </div>
    </div>
    <div>
      <div class="metric">
        <div class="metric-label">Energy produced</div>
        <div class="metric-value">{production.energy_produced}</div>
      </div>
      <div class="metric">
        <div class="metric-label">Energy used</div>
        <div class="metric-value">{production.energy_consumed}</div>
      </div>
      <div class="metric">
        <div class="metric-label">Balance</div>
        <div class="metric-value {'pos' if production.energy_balance >= 0 else 'neg'}">
          {production.energy_balance:+d}
        </div>
        <div class="metric-sub">factor {production.production_factor:.2f}x</div>
      </div>
    </div>
    <div>
      <div class="metric">
        <div class="metric-label">Fields</div>
        <div class="metric-value">{planet.fields_used} / {planet.fields_total}</div>
      </div>
      <div class="metric">
        <div class="metric-label">Temperature</div>
        <div class="metric-value">{planet.temp_min}° / {planet.temp_max}°C</div>
      </div>
      <div class="metric">
        <div class="metric-label">Coordinate</div>
        <div class="metric-value">{planet.galaxy}:{planet.system}:{planet.position}</div>
      </div>
    </div>
  </div>
</div>
"""


def _render_main_grid(
    planet: Planet,
    production,
    buildings: list[Building],
    active_queue: list[BuildQueue],
    logs: list[BuildQueue],
) -> str:
    return f"""
<div class="grid-2">
  <div>
    {_render_queue_card(active_queue)}
    {_render_activity_card(logs)}
  </div>
  <div>
    {_render_buildings_card(buildings)}
  </div>
</div>
"""


def _render_queue_card(active_queue: list[BuildQueue]) -> str:
    if not active_queue:
        rows = '<tr><td colspan="5" class="empty-state">queue empty</td></tr>'
    else:
        rows_list = []
        for q in active_queue:
            label = q.item_key.replace("_", " ").title()
            rows_list.append(
                f"<tr>"
                f"<td class='dim'>#{q.id}</td>"
                f"<td>{q.queue_type}</td>"
                f"<td><b>{label}</b></td>"
                f"<td class='right'>L{q.target_level}</td>"
                f"<td class='right success'>{_local_hhmmss(q.finished_at)} "
                f"<span class='dim'>({_remaining_str(q.finished_at)})</span></td>"
                f"</tr>"
            )
        rows = "".join(rows_list)
    return f"""
<div class="card">
  <h2 class="card-title">Build queue <small>{len(active_queue)} / 5 active</small></h2>
  <table>
    <thead>
      <tr><th>id</th><th>type</th><th>item</th><th class="right">to</th><th class="right">done at</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>
"""


def _render_activity_card(logs: list[BuildQueue]) -> str:
    if not logs:
        rows = '<tr><td colspan="3" class="empty-state">no activity yet</td></tr>'
    else:
        rows_list = []
        for q in logs:
            label = q.item_key.replace("_", " ").title()
            type_color = "success" if q.queue_type == "building" else "muted"
            rows_list.append(
                f"<tr>"
                f"<td class='dim'>{_local_hhmmss(q.finished_at)}</td>"
                f"<td class='{type_color}'>✓ {q.queue_type}</td>"
                f"<td><b>{label}</b> <span class='dim'>L{q.target_level}</span></td>"
                f"</tr>"
            )
        rows = "".join(rows_list)
    return f"""
<div class="card">
  <h2 class="card-title">Recent activity <small>last {len(logs)} events</small></h2>
  <table>
    <thead>
      <tr><th>when</th><th>type</th><th>item</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>
"""


def _render_buildings_card(buildings: list[Building]) -> str:
    # Sort by level desc, then by label
    sorted_b = sorted(buildings, key=lambda b: (-b.level, b.building_type))
    rows = []
    for b in sorted_b:
        try:
            bt = BuildingType(b.building_type)
            label = BUILDING_LABELS.get(bt, b.building_type)
        except ValueError:
            label = b.building_type
        lvl_style = "" if b.level > 0 else "muted"
        rows.append(
            f"<tr><td class='{lvl_style}'>{label}</td>"
            f"<td class='right {lvl_style}'>L{b.level}</td></tr>"
        )
    return f"""
<div class="card">
  <h2 class="card-title">Buildings <small>{sum(1 for b in buildings if b.level > 0)} built</small></h2>
  <table>
    <thead><tr><th>building</th><th class="right">level</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</div>
"""
