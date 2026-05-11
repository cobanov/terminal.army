"""Web HTML sayfalari - signup/signin formu, key gosterimi."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, status
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select

from backend.app.api.device import bind_token_to_code
from backend.app.deps import DBSession
from backend.app.models.user import User
from backend.app.security import create_access_token, hash_password, verify_password
from backend.app.services.universe_service import (
    assign_starting_planet,
    ensure_default_universe,
    ensure_user_researches,
)

router = APIRouter(tags=["web"])


_PAGE_CSS = """
  body {
    background: #000;
    color: #d4d4d4;
    font-family: 'SF Mono', Menlo, Monaco, 'Courier New', monospace;
    max-width: 720px;
    margin: 2rem auto;
    padding: 0 1.5rem;
    line-height: 1.5;
  }
  h1, h2 { color: #e5e5e5; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; }
  h1 { font-size: 1.5rem; margin: 0 0 0.2rem; }
  h1 span { color: #fbbf24; }
  .tagline { color: #737373; margin: 0 0 2rem; font-size: 0.85rem; }
  fieldset {
    border: 1px solid #262626;
    border-radius: 0;
    padding: 1rem 1.2rem;
    margin: 0 0 1.5rem;
    background: #0a0a0a;
  }
  legend {
    color: #fbbf24;
    padding: 0 0.4rem;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }
  label { display: block; margin-bottom: 0.6rem; font-size: 0.85rem; color: #a3a3a3; }
  input[type=text], input[type=email], input[type=password] {
    width: 100%;
    box-sizing: border-box;
    background: #000;
    color: #e5e5e5;
    border: 1px solid #262626;
    border-radius: 0;
    padding: 0.55rem 0.7rem;
    font-family: inherit;
    font-size: 0.95rem;
  }
  input:focus { outline: none; border-color: #fbbf24; }
  button {
    background: #171717;
    color: #fbbf24;
    border: 1px solid #fbbf24;
    padding: 0.55rem 1.4rem;
    border-radius: 0;
    font-family: inherit;
    font-size: 0.9rem;
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    transition: all 0.15s;
  }
  button:hover { background: #fbbf24; color: #000; }
  .ok { color: #84cc16; }
  .err { color: #ef4444; }
  .key {
    display: block;
    background: #000;
    color: #fbbf24;
    padding: 1rem;
    border-radius: 0;
    word-break: break-all;
    font-size: 0.8rem;
    user-select: all;
    border: 1px dashed #262626;
  }
  .hint { color: #737373; font-size: 0.8rem; margin: 0.4rem 0; }
  code { color: #fbbf24; background: #171717; padding: 0 0.25rem; }
  .banner {
    background: #0a0a0a;
    border-left: 2px solid #fbbf24;
    border-top: 1px solid #262626;
    border-right: 1px solid #262626;
    border-bottom: 1px solid #262626;
    padding: 0.7rem 1rem;
    margin: 0 0 1.5rem;
    color: #d4d4d4;
    font-size: 0.85rem;
  }
  .banner strong { color: #fbbf24; }
  .big { font-size: 1.1rem; color: #84cc16; margin: 0.3rem 0 0.8rem; }
  a { color: #fbbf24; text-decoration: none; }
  a:hover { color: #fde68a; }
"""


def _shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{title}</title>
<style>{_PAGE_CSS}</style>
</head>
<body>
{body}
</body>
</html>"""


def _form_body(code: str | None = None) -> str:
    qs = f"?code={code}" if code else ""
    banner = ""
    if code:
        banner = (
            '<p class="banner">'
            "Authenticating your terminal session. After signing in below, "
            "return to your <strong>ogame</strong> terminal."
            "</p>"
        )
    return f"""
<h1>Space <span>Galactic</span></h1>
<p class="tagline">Terminal-based OGame clone.</p>
{banner}

<fieldset>
  <legend>New account</legend>
  <form action="/signup{qs}" method="post">
    <label>Username <input type="text" name="username" minlength="3" maxlength="32" required autocomplete="username"></label>
    <label>Email <input type="email" name="email" required autocomplete="email"></label>
    <label>Password <input type="password" name="password" minlength="6" required autocomplete="new-password"></label>
    <button type="submit">Sign up</button>
  </form>
</fieldset>

<fieldset>
  <legend>Existing account</legend>
  <p class="hint">Password reset is not available yet. If you forgot it, create a new account.</p>
  <form action="/signin{qs}" method="post">
    <label>Username <input type="text" name="username" required autocomplete="username"></label>
    <label>Password <input type="password" name="password" required autocomplete="current-password"></label>
    <button type="submit">Sign in</button>
  </form>
</fieldset>
"""


def _success_body(username: str) -> str:
    return f"""
<h1>Space <span>Galactic</span></h1>
<p class="tagline">Signed in as <span class="ok">{username}</span></p>

<fieldset>
  <legend>Success</legend>
  <p class="big">Authentication complete.</p>
  <p class="hint">You can close this tab and return to your terminal. The <code>ogame</code> client should pick up your session within a couple of seconds.</p>
</fieldset>
"""


def _key_body(username: str, token: str) -> str:
    return f"""
<h1>Space <span>Galactic</span></h1>
<p class="tagline">Welcome, <span class="ok">{username}</span></p>

<fieldset>
  <legend>API key</legend>
  <p class="hint">Copy this key. The CLI accepts it via <code>OGAME_BACKEND_TOKEN</code> env or manual paste:</p>
  <span class="key">{token}</span>
  <p class="hint">This key is long-lived. If you lose it, sign in again from this page.</p>
</fieldset>

<p><a href="/signup" >&larr; back to sign in</a></p>
"""


def _err_body(msg: str, code: str | None = None) -> str:
    qs = f"?code={code}" if code else ""
    return f"""
<h1>Space <span>Galactic</span></h1>
<p class="err">{msg}</p>
<p><a href="/signup{qs}" >&larr; go back</a></p>
"""


@router.get("/", response_class=HTMLResponse)
async def index(code: str | None = None) -> str:
    return _shell("Space Galactic", _form_body(code))


@router.get("/login", response_class=HTMLResponse)
async def login_page(code: str | None = None) -> str:
    """Alias for /signup; used by CLI's device flow URL."""
    return _shell("Sign in - Space Galactic", _form_body(code))


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(code: str | None = None) -> str:
    return _shell("Sign up - Space Galactic", _form_body(code))


@router.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    db: DBSession,
    username: Annotated[str, Form(min_length=3, max_length=32)],
    email: Annotated[str, Form()],
    password: Annotated[str, Form(min_length=6)],
    code: str | None = None,
) -> HTMLResponse:
    existing = await db.execute(
        select(User).where(or_(User.username == username, User.email == email))
    )
    if existing.scalar_one_or_none() is not None:
        return HTMLResponse(
            _shell(
                "Error",
                _err_body("That username or email is already taken.", code=code),
            ),
            status_code=status.HTTP_409_CONFLICT,
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
            return HTMLResponse(
                _shell(
                    "Error",
                    _err_body(
                        "Auth code is invalid or expired. Restart ogame in your terminal.",
                    ),
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return HTMLResponse(_shell("Signed in", _success_body(username)))

    return HTMLResponse(_shell("Key - Space Galactic", _key_body(username, token)))


@router.post("/signin", response_class=HTMLResponse)
async def signin_submit(
    db: DBSession,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    code: str | None = None,
) -> HTMLResponse:
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return HTMLResponse(
            _shell("Error", _err_body("Wrong username or password.", code=code)),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    token = create_access_token(user.id)

    if code:
        bound = await bind_token_to_code(db, code=code, token=token, user_id=user.id)
        if not bound:
            return HTMLResponse(
                _shell(
                    "Error",
                    _err_body(
                        "Auth code is invalid or expired. Restart ogame in your terminal.",
                    ),
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return HTMLResponse(_shell("Signed in", _success_body(username)))

    return HTMLResponse(_shell("Key - Space Galactic", _key_body(username, token)))
