from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.app.api.admin import router as admin_router
from backend.app.api.admin_ui import router as admin_ui_router
from backend.app.api.alliance import router as alliance_router
from backend.app.api.auth import router as auth_router
from backend.app.api.building import router as building_router
from backend.app.api.device import router as device_router
from backend.app.api.fleet import router as fleet_router
from backend.app.api.galaxy import router as galaxy_router
from backend.app.api.leaderboard import router as leaderboard_router
from backend.app.api.planet import router as planet_router
from backend.app.api.research import router as research_router
from backend.app.api.shipyard import router as shipyard_router
from backend.app.api.social import router as social_router
from backend.app.api.stats import router as stats_router
from backend.app.api.universe import router as universe_router
from backend.app.api.web import router as web_router
from backend.app.web_templates import STATIC_DIR
from backend.app.config import get_settings
from backend.app.db import AsyncSessionLocal, init_db
from backend.app.scheduler import start_scheduler, stop_scheduler
from backend.app.services.universe_service import (
    backfill_planet_buildings,
    backfill_user_researches,
    ensure_default_universe,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Sqlite icin Alembic gerekmeden create_all calistir; postgres production'da
    # Alembic migration kullanmalisin ama dev rahatligi icin idempotent.
    await init_db()
    async with AsyncSessionLocal() as db:
        await ensure_default_universe(
            db, name=settings.default_universe_name, speed=settings.default_universe_speed
        )
        await backfill_planet_buildings(db)
        await backfill_user_researches(db)
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="OGame Backend", version="0.1.0", lifespan=lifespan)

    origins = (
        ["*"] if settings.cors_origins.strip() == "*" else
        [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(web_router)
    app.include_router(auth_router)
    app.include_router(device_router)
    app.include_router(universe_router)
    app.include_router(planet_router)
    app.include_router(building_router)
    app.include_router(research_router)
    app.include_router(galaxy_router)
    app.include_router(social_router)
    app.include_router(shipyard_router)
    app.include_router(fleet_router)
    app.include_router(admin_router)
    app.include_router(admin_ui_router)
    app.include_router(stats_router)
    app.include_router(alliance_router, prefix="/api")
    app.include_router(leaderboard_router, prefix="/api")

    # Static files (CSS, etc.)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


app = create_app()
