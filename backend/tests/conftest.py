from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Override DATABASE_URL early so config picks up the test DB.
_tmp_db_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db_file.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp_db_file.name}"
os.environ["JWT_SECRET"] = "test-secret"

# Cache clear so settings re-read env.
from backend.app.config import get_settings  # noqa: E402

get_settings.cache_clear()

# Disable rate limiting under pytest. With the in-process slowapi limiter,
# back-to-back tests share state and hit the 5/minute signup cap.
from backend.app.rate_limit import limiter  # noqa: E402

limiter.enabled = False


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def app():
    from backend.app.db import engine, init_db
    from backend.app.main import create_app
    from backend.app.models import all_models  # noqa: F401

    # Recreate schema for each test.
    async with engine.begin() as conn:
        from backend.app.db import Base

        await conn.run_sync(Base.metadata.drop_all)
    await init_db()

    app = create_app()
    yield app


@pytest_asyncio.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Trigger app startup
        async with app.router.lifespan_context(app):
            yield c
