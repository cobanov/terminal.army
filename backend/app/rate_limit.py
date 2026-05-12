"""Per-IP rate limiting.

Endpoints exposed to unauthenticated callers (signup, login, device-auth)
or to expensive operations (fleet send) need throttling to discourage
credential stuffing, brute force, and abuse. We use slowapi which wraps
limits.

Wire-up:
    from backend.app.rate_limit import limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

Per-endpoint usage:
    @limiter.limit("5/minute")
    async def signin(request: Request, ...):
        ...

The `request: Request` parameter MUST appear in the signature — slowapi
extracts the client IP from it.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Module-level singleton so individual routers can import + decorate.
limiter = Limiter(key_func=get_remote_address)
