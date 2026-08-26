"""
Cloud backup scheduler — runs weekly backup for all connected users.
Uses APScheduler (already in requirements.txt) with AsyncIOScheduler.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def init_backup_scheduler():
    """Initialize the backup scheduler. Call from server.py startup."""
    # Run every Sunday at 2 AM UTC (low traffic time)
    scheduler.add_job(
        _run_all_backups,
        CronTrigger(day_of_week="sun", hour=2, minute=0),
        id="weekly_backup",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Cloud backup scheduler started — weekly backups at Sunday 2 AM UTC")


async def _run_all_backups():
    """Wrapper to import and run scheduled backups (avoids circular import at module level)."""
    from services.backup_service import run_scheduled_backups
    try:
        await run_scheduled_backups()
    except Exception as e:
        logger.error(f"Scheduled backup run failed: {e}")


def shutdown_backup_scheduler():
    """Shutdown scheduler on app exit."""
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass