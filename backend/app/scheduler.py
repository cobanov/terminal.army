"""APScheduler: tamamlanan queue itemlarini periyodik islet."""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.app.config import get_settings
from backend.app.db import AsyncSessionLocal
from backend.app.services.fleet_service import (
    process_fleet_arrivals,
    process_fleet_returns,
)
from backend.app.services.queue_service import process_completed_queue

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _tick() -> None:
    try:
        async with AsyncSessionLocal() as db:
            applied = await process_completed_queue(db)
            arrivals = await process_fleet_arrivals(db)
            returns = await process_fleet_returns(db)
            if applied + arrivals + returns > 0:
                logger.info(
                    "scheduler: queue=%d arrivals=%d returns=%d",
                    applied, arrivals, returns,
                )
    except Exception:
        logger.exception("scheduler tick failed")


def start_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    settings = get_settings()
    sched = AsyncIOScheduler()
    sched.add_job(
        _tick,
        "interval",
        seconds=settings.scheduler_interval_seconds,
        id="process_completed_queue",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    return sched


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


async def run_tick_once() -> int:
    """Test'lerden cagrilabilir."""
    async with AsyncSessionLocal() as db:
        return await process_completed_queue(db)


__all__ = ["asyncio", "run_tick_once", "start_scheduler", "stop_scheduler"]
