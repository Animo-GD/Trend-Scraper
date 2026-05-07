"""
Trends query router — search and filter stored trends.
"""
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Query

from app.database import get_supabase

router = APIRouter(prefix="/trends", tags=["trends"])

Platform = Literal["x", "instagram", "facebook", "tiktok"]

TABLE_MAP = {
    "x": "x_trends",
    "instagram": "instagram_trends",
    "facebook": "facebook_trends",
    "tiktok": "tiktok_trends",
}


def _build_query(db, table: str, keyword: Optional[str], since: Optional[str], limit: int):
    q = (
        db.table(table)
        .select("*")
        .order("scraped_at", desc=True)
        .limit(limit)
    )
    if keyword:
        q = q.ilike("keyword", f"%{keyword}%")
    if since:
        q = q.gte("scraped_at", since)
    return q


@router.get("/")
async def get_all_trends(
    platform: Optional[Platform] = None,
    keyword: Optional[str] = Query(None, description="Filter by keyword (partial match)"),
    since: Optional[str] = Query(None, description="ISO8601 datetime — only return items scraped after this"),
    limit: int = Query(50, le=200),
):
    """Get trends across all platforms (or a specific one)."""
    db = get_supabase()
    results = {}

    platforms = [platform] if platform else list(TABLE_MAP.keys())
    for plat in platforms:
        table = TABLE_MAP[plat]
        resp = _build_query(db, table, keyword, since, limit).execute()
        results[plat] = resp.data or []

    return {"trends": results}


@router.get("/{platform}")
async def get_platform_trends(
    platform: Platform,
    keyword: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Get trends for a specific platform."""
    db = get_supabase()
    table = TABLE_MAP[platform]
    resp = _build_query(db, table, keyword, since, limit).execute()
    return {"platform": platform, "count": len(resp.data or []), "trends": resp.data}


@router.get("/{platform}/search")
async def search_trends(
    platform: Platform,
    q: str = Query(..., description="Full-text search query"),
    limit: int = Query(50, le=200),
):
    """Full-text search within trend content for a platform."""
    db = get_supabase()
    table = TABLE_MAP[platform]
    content_col = "caption" if platform == "instagram" else "content"

    # Use ilike for broader compatibility across languages and without needing FTS indexes
    resp = (
        db.table(table)
        .select("*")
        .ilike(content_col, f"%{q}%")
        .order("scraped_at", desc=True)
        .limit(limit)
        .execute()
    )
    return {"platform": platform, "query": q, "count": len(resp.data or []), "results": resp.data}
