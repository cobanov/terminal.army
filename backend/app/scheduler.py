"""APScheduler: periodic background work.

Two jobs:
- `_tick` every N seconds: apply completed queue items, fleet arrivals, returns.
- `_gc_device_sessions` hourly: prune expired auth codes so an unbounded
  attacker cannot grow the table forever.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete

from backend.app.config import get_settings
from backend.app.db import AsyncSessionLocal
from backend.app.models.device_session import DeviceSession
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
                    applied,
                    arrivals,
                    returns,
                )
    except Exception:
        logger.exception("scheduler tick failed")


async def _gc_device_sessions() -> None:
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                delete(DeviceSession).where(DeviceSession.expires_at < datetime.now(UTC))
            )
            await db.commit()
            # CursorResult.rowcount exists at runtime; Result generic type
            # doesn't expose it, but the async delete returns a cursor.
            n = getattr(result, "rowcount", 0) or 0
            if n:
                logger.info("scheduler: pruned %d expired device sessions", n)
    except Exception:
        logger.exception("device-session GC failed")


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
    sched.add_job(
        _gc_device_sessions,
        "interval",
        minutes=15,
        id="gc_device_sessions",
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


__all__ = ["run_tick_once", "start_scheduler", "stop_scheduler"]
