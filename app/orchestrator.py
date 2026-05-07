"""
Scrape orchestrator — runs all active keywords across all platforms,
saves results to Supabase, and logs jobs.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from app.database import get_supabase
from app.scrapers import XScraper, InstagramScraper, FacebookScraper

logger = logging.getLogger(__name__)

PLATFORM_SCRAPERS = {
    "x": XScraper,
    "instagram": InstagramScraper,
    "facebook": FacebookScraper,
    "tiktok": TikTokScraper,
}

TABLE_MAP = {
    "x": "x_trends",
    "instagram": "instagram_trends",
    "facebook": "facebook_trends",
    "tiktok": "tiktok_trends",
}


async def run_scrape(
    platform: Optional[str] = None,
    keyword_id: Optional[str] = None,
    limit: int = 30,
) -> dict:
    """
    Main scrape runner.
    - If platform is None, scrape all active keywords across all platforms.
    - If platform is set, only scrape that platform.
    - If keyword_id is set, only scrape that specific keyword.
    Returns a summary dict.
    """
    db = get_supabase()
    summary = {"total_found": 0, "by_platform": {}, "errors": []}

    # Fetch keywords
    query = db.table("keywords").select("*").eq("active", True)
    if platform:
        query = query.eq("platform", platform)
    if keyword_id:
        query = query.eq("id", keyword_id)

    kw_resp = query.execute()
    keywords = kw_resp.data or []

    if not keywords:
        logger.info("[Orchestrator] No active keywords found.")
        return summary

    logger.info("[Orchestrator] Running scrape for %d keywords.", len(keywords))

    # Group by platform
    platform_groups: dict[str, list[dict]] = {}
    for kw in keywords:
        platform_groups.setdefault(kw["platform"], []).append(kw)

    for plat, kw_list in platform_groups.items():
        scraper_cls = PLATFORM_SCRAPERS.get(plat)
        if not scraper_cls:
            logger.warning("[Orchestrator] No scraper for platform '%s'.", plat)
            continue

        plat_found = 0
        for kw in kw_list:
            job_id = _start_job(db, plat, kw["keyword"])
            try:
                scraper = scraper_cls()
                rows = await scraper.run(kw["keyword"], kw["id"], limit=limit)

                if rows:
                    _upsert_rows(db, plat, rows)
                    plat_found += len(rows)

                _finish_job(db, job_id, "completed", len(rows))
                logger.info(
                    "[%s] Saved %d items for keyword '%s'.", plat, len(rows), kw["keyword"]
                )
            except Exception as exc:
                logger.error("[%s] Failed keyword '%s': %s", plat, kw["keyword"], exc)
                _finish_job(db, job_id, "failed", 0, str(exc))
                summary["errors"].append(
                    {"platform": plat, "keyword": kw["keyword"], "error": str(exc)}
                )

            # Small delay between keywords on same platform
            await asyncio.sleep(2)

        summary["by_platform"][plat] = plat_found
        summary["total_found"] += plat_found

    return summary


def _upsert_rows(db, platform: str, rows: list[dict]) -> None:
    table = TABLE_MAP[platform]
    id_field = {
        "x": "tweet_id",
        "instagram": "post_id",
        "facebook": "post_id",
        "tiktok": "video_id",
    }.get(platform, "post_id")

    # Filter out rows with no unique ID (can't upsert without it)
    valid_rows = [r for r in rows if r.get(id_field)]
    if not valid_rows:
        return

    db.table(table).upsert(valid_rows, on_conflict=id_field).execute()


def _start_job(db, platform: str, keyword: str) -> Optional[str]:
    try:
        resp = (
            db.table("scrape_jobs")
            .insert({"platform": platform, "keyword": keyword, "status": "running"})
            .execute()
        )
        return resp.data[0]["id"] if resp.data else None
    except Exception:
        return None


def _finish_job(
    db,
    job_id: Optional[str],
    status: str,
    items_found: int,
    error: Optional[str] = None,
) -> None:
    if not job_id:
        return
    try:
        db.table("scrape_jobs").update(
            {
                "status": status,
                "items_found": items_found,
                "error": error,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", job_id).execute()
    except Exception:
        pass
