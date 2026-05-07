"""
TikTok Scraper
Uses Playwright to scrape TikTok search results.
"""
import asyncio
import logging
import re
from typing import Optional

from playwright.async_api import BrowserContext, Page, Response

from app.config import settings
from app.scrapers.base import (
    BaseScraper,
    human_delay,
    human_scroll,
    DELAY_MEDIUM,
    DELAY_SHORT,
    DELAY_LONG,
)

logger = logging.getLogger(__name__)


def _parse_count(text: str) -> int:
    if not text:
        return 0
    text = text.lower().strip()
    try:
        if "k" in text:
            return int(float(text.replace("k", "").replace(",", "")) * 1000)
        if "m" in text:
            return int(float(text.replace("m", "").replace(",", "")) * 1000000)
        return int(re.sub(r"[^\d]", "", text) or 0)
    except Exception:
        return 0


class TikTokScraper(BaseScraper):
    platform = "tiktok"

    async def _inject_cookies(self, context: BrowserContext) -> None:
        if not settings.tiktok_session_id:
            logger.warning("[TikTok] Session ID not set.")
            return

        cookies = [
            {
                "name": "sessionid",
                "value": settings.tiktok_session_id,
                "domain": ".tiktok.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
            }
        ]
        await context.add_cookies(cookies)

    async def scrape(self, keyword: str, keyword_id: str, limit: int = 30) -> list[dict]:
        page = await self._new_page()
        results: list[dict] = []

        try:
            # TikTok search URL
            search_url = f"https://www.tiktok.com/search?q={keyword.replace(' ', '%20')}"
            logger.info("[TikTok] Searching: %s", search_url)

            await page.goto(search_url, wait_until="networkidle", timeout=60000)
            await human_delay(DELAY_LONG)

            # Check for bot detection but continue if items are found
            # (TikTok often has "verify" text in JS bundles even when results are visible)
            items = await self._find_items(page)
            
            if not items:
                # If no items, then check if it's really a bot wall
                if await self._check_bot_detection(page, keyword):
                    return results
                
                # Try scrolling once to see if it loads
                await human_scroll(page, scrolls=2)
                await human_delay(DELAY_MEDIUM)
                items = await self._find_items(page)

            if not items:
                logger.warning("[TikTok] No items found for '%s'", keyword)
                return results

            logger.info("[TikTok] Found %d items on page", len(items))

            for item in items[:limit]:
                try:
                    # Video link
                    link_el = await item.query_selector("a[href*='/video/']")
                    url = await link_el.get_attribute("href") if link_el else None
                    if not url: continue
                    
                    video_id = url.split("/")[-1].split("?")[0] if url else None
                    if not video_id: continue

                    # Author
                    author_el = await item.query_selector("[data-e2e='search_video-item-author-name'], [class*='PAuthorName']")
                    author_username = await author_el.inner_text() if author_el else None
                    
                    # Fallback: Extract from URL
                    if not author_username and url and "@" in url:
                        # URL format: https://www.tiktok.com/@username/video/123
                        match = re.search(r"@([^/?]+)", url)
                        if match:
                            author_username = match.group(1)

                    # Content / Description
                    desc_el = await item.query_selector("[data-e2e='search_video-item-desc'], [class*='DivDesContainer']")
                    content = await desc_el.inner_text() if desc_el else ""

                    # Engagement
                    likes = 0
                    likes_el = await item.query_selector("[data-e2e='like-count'], [class*='StrongLikeCount']")
                    if likes_el:
                        likes = _parse_count(await likes_el.inner_text())

                    results.append({
                        "keyword_id": keyword_id,
                        "keyword": keyword,
                        "video_id": video_id,
                        "author_username": author_username,
                        "content": content,
                        "hashtags": re.findall(r"#(\w+)", content),
                        "likes": likes,
                        "url": url,
                        "scraped_at": None,
                    })
                except Exception as e:
                    logger.debug("[TikTok] Item parse error: %s", e)

        except Exception as exc:
            logger.error("[TikTok] Scrape error: %s", exc)
        finally:
            await page.close()

        return results

    async def _find_items(self, page: Page):
        """Try multiple selectors to find video items."""
        selectors = [
            "[data-e2e='search_video-item']",
            "div[class*='DivItemContainerV2']",
            "div[class*='DivVideoItemContainer']"
        ]
        for selector in selectors:
            items = await page.query_selector_all(selector)
            if items:
                return items
        return []
