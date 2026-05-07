"""
APScheduler-based scheduler that runs scrapes at random intervals
between SCRAPE_INTERVAL_MIN_HOURS and SCRAPE_INTERVAL_MAX_HOURS.
This randomization prevents detectable bot patterns.
"""
import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from app.config import settings
from app.orchestrator import run_scrape

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def _next_run_time() -> datetime:
    """Pick a random time between min and max hours from now."""
    delay_hours = random.uniform(
        settings.scrape_interval_min_hours,
        settings.scrape_interval_max_hours,
    )
    delay_seconds = delay_hours * 3600
    run_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    logger.info(
        "[Scheduler] Next scrape in %.1f hours (at %s UTC).",
        delay_hours,
        run_at.strftime("%Y-%m-%d %H:%M"),
    )
    return run_at


async def _scheduled_scrape() -> None:
    """Run scrape then schedule the next one at a new random time."""
    logger.info("[Scheduler] Starting scheduled scrape run.")
    try:
        summary = await run_scrape()
        logger.info("[Scheduler] Scrape complete: %s", summary)
    except Exception as exc:
        logger.error("[Scheduler] Scrape failed: %s", exc)
    finally:
        # Schedule the NEXT run immediately after this one finishes
        _schedule_next()


def _schedule_next() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.add_job(
            _scheduled_scrape,
            trigger=DateTrigger(run_date=_next_run_time()),
            id="scrape_job",
            replace_existing=True,
            misfire_grace_time=600,
        )


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def start_scheduler() -> None:
    sched = get_scheduler()
    if not sched.running:
        sched.start()
        _schedule_next()
        logger.info("[Scheduler] Started with random interval %s–%s hours.",
                    settings.scrape_interval_min_hours,
                    settings.scrape_interval_max_hours)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped.")


def get_next_run_info() -> dict:
    """Return info about the next scheduled run."""
    sched = get_scheduler()
    job = sched.get_job("scrape_job")
    if job and job.next_run_time:
        return {
            "next_run_at": job.next_run_time.isoformat(),
            "running": sched.running,
        }
    return {"next_run_at": None, "running": sched.running}
