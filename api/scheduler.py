import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from api.config import get_settings
from api.database import _db_path
from api.services import scraper_service

_scheduler = AsyncIOScheduler()


async def _refresh_job():
    async with aiosqlite.connect(_db_path()) as db:
        db.row_factory = aiosqlite.Row
        count = await scraper_service.refresh_rates(db)
        print(f"[scheduler] Refreshed {count} rate entries.")


async def _cleanup_job():
    """Prune request_log rows older than 48 hours."""
    async with aiosqlite.connect(_db_path()) as db:
        await db.execute(
            "DELETE FROM request_log WHERE ts < datetime('now', '-2 days')"
        )
        await db.commit()


def start_scheduler():
    hours = get_settings().scraper_refresh_hours
    _scheduler.add_job(_refresh_job, IntervalTrigger(hours=hours), id="refresh_rates")
    _scheduler.add_job(_cleanup_job, IntervalTrigger(hours=24), id="cleanup_logs")
    _scheduler.start()


def stop_scheduler():
    _scheduler.shutdown(wait=False)
