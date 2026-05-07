"""
Scrape trigger router — manual scrape endpoints.
"""
import asyncio
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.orchestrator import run_scrape
from app.scheduler import get_next_run_info

router = APIRouter(prefix="/scrape", tags=["scrape"])

Platform = Literal["x", "instagram", "facebook", "tiktok"]

# Simple in-memory lock to prevent concurrent scrapes
_running = False


class ScrapeRequest(BaseModel):
    platform: Optional[Platform] = None
    keyword_id: Optional[str] = None
    limit: int = 30


async def _run_in_background(platform, keyword_id, limit):
    global _running
    try:
        await run_scrape(platform=platform, keyword_id=keyword_id, limit=limit)
    finally:
        _running = False


@router.post("/")
async def trigger_scrape(body: ScrapeRequest, background_tasks: BackgroundTasks):
    """Trigger a scrape manually. Runs in background and returns immediately."""
    global _running
    if _running:
        raise HTTPException(status_code=409, detail="A scrape is already running.")
    _running = True
    background_tasks.add_task(
        _run_in_background, body.platform, body.keyword_id, body.limit
    )
    return {
        "status": "started",
        "message": "Scrape started in background.",
        "platform": body.platform or "all",
        "keyword_id": body.keyword_id,
    }


@router.get("/status")
async def scrape_status():
    """Returns whether a scrape is currently running and the next scheduled run."""
    return {
        "scrape_running": _running,
        "scheduler": get_next_run_info(),
    }


@router.get("/jobs")
async def scrape_jobs(limit: int = 20, platform: Optional[Platform] = None):
    """Return recent scrape job history."""
    from app.database import get_supabase
    db = get_supabase()
    query = (
        db.table("scrape_jobs")
        .select("*")
        .order("started_at", desc=True)
        .limit(limit)
    )
    if platform:
        query = query.eq("platform", platform)
    resp = query.execute()
    return {"jobs": resp.data}
