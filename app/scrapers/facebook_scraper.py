"""
Facebook Scraper
Uses Playwright to scrape Facebook search results.
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


class FacebookScraper(BaseScraper):
    platform = "facebook"

    async def _inject_cookies(self, context: BrowserContext) -> None:
        if not settings.facebook_c_user or not settings.facebook_xs:
            logger.warning("[Facebook] Cookie credentials not set.")
            return

        cookies = [
            {
                "name": "c_user",
                "value": settings.facebook_c_user,
                "domain": ".facebook.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
            },
            {
                "name": "xs",
                "value": settings.facebook_xs,
                "domain": ".facebook.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
            },
        ]
        if settings.facebook_datr:
            cookies.append({
                "name": "datr",
                "value": settings.facebook_datr,
                "domain": ".facebook.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
            })
        await context.add_cookies(cookies)

    async def scrape(self, keyword: str, keyword_id: str, limit: int = 30) -> list[dict]:
        page = await self._new_page()
        results: list[dict] = []

        try:
            # Facebook search URL for posts
            search_url = f"https://www.facebook.com/search/posts/?q={keyword.replace(' ', '%20')}"
            logger.info("[Facebook] Searching: %s", search_url)

            # Warm up with home page first to load cookies properly
            await page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
            await human_delay(DELAY_MEDIUM)

            await page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            await human_delay(DELAY_LONG)

            # Check for bot detection
            items = await page.query_selector_all("div[role='article']")
            
            if not items:
                if await self._check_bot_detection(page, keyword):
                    return results

            # Scroll to load more
            await human_scroll(page, scrolls=3)
            await human_delay(DELAY_MEDIUM)

            items = await page.query_selector_all("div[role='article']")
            logger.info("[Facebook] Found %d items on page", len(items))

            for item in items[:limit]:
                try:
                    # Post content
                    # Facebook's DOM is highly complex, using role='article' is the best entry point
                    content_el = await item.query_selector("div[data-ad-preview='message'], div[data-testid='post_message']")
                    content = await content_el.inner_text() if content_el else ""

                    # Author & URL
                    # Often found in the header of the article
                    link_el = await item.query_selector("a[href*='/posts/'], a[href*='/permalink.php'], a[href*='/videos/']")
                    url = await link_el.get_attribute("href") if link_el else None
                    if url and not url.startswith("http"):
                        url = f"https://www.facebook.com{url}"

                    author_el = await item.query_selector("h3 a, strong a")
                    author_name = await author_el.inner_text() if author_el else "Unknown"

                    # Engagement
                    reactions = 0
                    reactions_el = await item.query_selector("[aria-label*='Like'], [aria-label*='reaction']")
                    if reactions_el:
                        reactions = _parse_count(await reactions_el.get_attribute("aria-label"))

                    if not content and not url:
                        continue

                    post_id = None
                    if url:
                        # Extract post ID from URL
                        # Format: .../posts/12345 or .../permalink.php?story_fbid=12345
                        id_match = re.search(r"/posts/(\d+)", url) or re.search(r"story_fbid=(\d+)", url)
                        post_id = id_match.group(1) if id_match else f"fb_{hash(url)}"

                    results.append({
                        "keyword_id": keyword_id,
                        "keyword": keyword,
                        "post_id": post_id,
                        "author_name": author_name,
                        "content": content,
                        "reactions": reactions,
                        "url": url,
                        "scraped_at": None,
                    })
                except Exception as e:
                    logger.debug("[Facebook] Item parse error: %s", e)

        except Exception as exc:
            logger.error("[Facebook] Scrape error: %s", exc)
        finally:
            await page.close()

        return results
