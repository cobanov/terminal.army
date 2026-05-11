from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from backend.app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()

connect_args: dict[str, Any] = {}
if settings.database_url.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args=connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """Create all tables. Used at startup when not using Alembic (e.g. SQLite dev)."""
    from backend.app.models import all_models  # noqa: F401  (register models)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
