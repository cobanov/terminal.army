"""Lightweight CSRF guard for cookie-auth state-changing requests.

Rationale: the API surface uses two auth mechanisms.

  * Bearer-token endpoints (JSON API for the TUI / external scripts):
    no CSRF risk — a third-party site can read neither the bearer token
    nor send it cross-origin without explicit JS.

  * Cookie endpoints (everything under /admin/* and the web dashboard
    forms): a logged-in admin who visits attacker.com can be tricked
    into auto-submitting a hidden <form> back to terminal.army, and
    the cookie tags along.

This middleware blocks the cookie-attack window using the standard
Origin / Referer check: any mutating verb (POST/PUT/PATCH/DELETE) that
carries our session cookie must also present an Origin or Referer
matching one of our allowed origins. No token bookkeeping, no template
changes.

Allowed origins come from the existing CORS_ORIGINS setting + the
request's own scheme://host (so a user hitting https://terminal.army
posting to https://terminal.army always passes).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

# These cookie names mark a state-changing browser session. If the
# request carries one of these cookies on a mutating verb, we require
# a matching Origin/Referer.
_SESSION_COOKIE_NAMES = frozenset({"ogame_token"})

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CSRFOriginMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        super().__init__(app)
        # Normalize: strip trailing slashes, lowercase scheme+host.
        self._allowed = {self._normalize(o) for o in allowed_origins if o}

    @staticmethod
    def _normalize(raw: str) -> str:
        raw = raw.strip().rstrip("/")
        if "://" not in raw:
            return raw
        p = urlparse(raw)
        return f"{p.scheme.lower()}://{(p.netloc or '').lower()}"

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method not in _MUTATING_METHODS:
            return await call_next(request)

        # No session cookie → not a browser form attack vector.
        has_session = any(c in request.cookies for c in _SESSION_COOKIE_NAMES)
        if not has_session:
            return await call_next(request)

        # Resolve the request's "self" origin so a same-origin form
        # always passes regardless of what CORS_ORIGINS is set to.
        # Prefer X-Forwarded-* when set by a known reverse proxy.
        fwd_proto = request.headers.get("x-forwarded-proto")
        scheme = (fwd_proto or request.url.scheme).split(",")[0].strip().lower()
        host = (
            request.headers.get("x-forwarded-host")
            or request.headers.get("host")
            or request.url.netloc
        )
        host = host.split(",")[0].strip().lower()
        same_origin = f"{scheme}://{host}"

        allowed = set(self._allowed)
        allowed.add(self._normalize(same_origin))

        # Browsers always send Origin on cross-origin POSTs and on
        # same-origin POSTs from forms with method=post. If Origin is
        # missing, fall back to Referer.
        origin = request.headers.get("origin") or ""
        if origin:
            if self._normalize(origin) not in allowed:
                return _refuse("origin mismatch")
            return await call_next(request)

        referer = request.headers.get("referer") or ""
        if referer:
            ref_origin = self._normalize(
                urlparse(referer).scheme + "://" + urlparse(referer).netloc
                if "://" in referer
                else referer
            )
            if ref_origin not in allowed:
                return _refuse("referer mismatch")
            return await call_next(request)

        # Cookie + mutating verb + no Origin + no Referer = treat as
        # hostile (real browsers always set at least one of them on
        # form submissions).
        return _refuse("missing origin and referer")


def _refuse(reason: str) -> Response:
    return JSONResponse(
        status_code=403,
        content={"detail": f"csrf check failed: {reason}"},
    )
