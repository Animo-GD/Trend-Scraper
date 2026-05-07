"""
Instagram Scraper
Uses Playwright stealth with injected session cookies.
Scrapes the hashtag explore page for top posts.
"""
import logging
import re
import json
from typing import Optional

from playwright.async_api import BrowserContext, Page

from app.config import settings
from app.scrapers.base import (
    BaseScraper,
    human_delay,
    human_scroll,
    DELAY_LONG,
    DELAY_MEDIUM,
    DELAY_SHORT,
)

logger = logging.getLogger(__name__)

_IG_BASE = "https://www.instagram.com"


def _extract_hashtags(text: str) -> list[str]:
    return re.findall(r"#(\w+)", text or "")


def _safe_int(val) -> int:
    try:
        return int(str(val).replace(",", "").replace(".", "").strip())
    except Exception:
        return 0


class InstagramScraper(BaseScraper):
    platform = "instagram"

    async def _inject_cookies(self, context: BrowserContext) -> None:
        if not settings.instagram_session_id:
            logger.warning("Instagram SESSION_ID not configured.")
            return

        cookies = [
            {
                "name": "sessionid",
                "value": settings.instagram_session_id,
                "domain": ".instagram.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
            },
        ]
        if settings.instagram_csrf_token:
            cookies.append(
                {
                    "name": "csrftoken",
                    "value": settings.instagram_csrf_token,
                    "domain": ".instagram.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": False,
                    "sameSite": "Lax",
                }
            )
        await context.add_cookies(cookies)

    # ------------------------------------------------------------------ #
    #  Scraping logic                                                       #
    # ------------------------------------------------------------------ #

    async def scrape(self, keyword: str, keyword_id: str, limit: int = 30) -> list[dict]:
        page = await self._new_page()
        results: list[dict] = []

        try:
            tag = keyword.lstrip("#")

            # First navigate to IG home to apply cookies
            logger.info("[Instagram] Warming up session at instagram.com...")
            await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
            await human_delay(DELAY_MEDIUM)

            # Check bot / login wall on home
            if await self._check_bot_detection(page, keyword):
                return results

            if "/accounts/login" in page.url or "login" in page.url.lower():
                logger.error("[Instagram] Session expired – redirected to login.")
                return results

            # Try hashtag explore page — Instagram has two possible URLs
            for url_template in [
                f"https://www.instagram.com/explore/tags/{tag}/",
                f"https://www.instagram.com/explore/search/keyword/?q=%23{tag}",
            ]:
                logger.info("[Instagram] Navigating to %s", url_template)
                await page.goto(url_template, wait_until="domcontentloaded", timeout=30000)
                await human_delay(DELAY_LONG)

                if await self._check_bot_detection(page, keyword):
                    return results

                if "/accounts/login" not in page.url and "login" not in page.url.lower():
                    break  # Found a working URL

            # Try to intercept the GraphQL response for hashtag data
            results = await self._scrape_via_api(page, tag, keyword_id, limit)

            if not results:
                # Fallback: parse DOM
                results = await self._scrape_via_dom(page, tag, keyword_id, limit)

        except Exception as exc:
            logger.error("[Instagram] Error scraping '%s': %s", keyword, exc)
        finally:
            await page.close()

        return results

    async def _scrape_via_api(
        self, page: Page, tag: str, keyword_id: str, limit: int
    ) -> list[dict]:
        """Intercept Instagram's internal GraphQL/API calls for hashtag data."""
        results: list[dict] = []
        api_data: list[dict] = []

        async def handle_response(response):
            try:
                if "api/v1/tags" in response.url or "graphql/query" in response.url:
                    if response.status == 200:
                        try:
                            body = await response.json()
                            api_data.append(body)
                        except Exception:
                            pass
            except Exception:
                pass

        page.on("response", handle_response)

        # Scroll to trigger more API calls
        await human_scroll(page, scrolls=3)
        await human_delay(DELAY_MEDIUM)

        page.remove_listener("response", handle_response)

        for data in api_data:
            results.extend(self._parse_api_data(data, tag, keyword_id))
            if len(results) >= limit:
                break

        return results[:limit]

    def _parse_api_data(self, data: dict, tag: str, keyword_id: str) -> list[dict]:
        """Parse Instagram API response structure."""
        posts = []
        try:
            # Handles various IG API response shapes
            sections = (
                data.get("data", {}).get("hashtag", {}).get("edge_hashtag_to_top_posts", {}).get("edges", [])
                or data.get("sections", [])
                or []
            )
            for edge in sections:
                node = edge.get("node", edge)
                media = node.get("media", node)
                post = self._parse_media_node(media, tag, keyword_id)
                if post:
                    posts.append(post)
        except Exception as exc:
            logger.debug("[Instagram] API parse error: %s", exc)
        return posts

    def _parse_media_node(self, node: dict, keyword: str, keyword_id: str) -> Optional[dict]:
        try:
            post_id = node.get("id") or node.get("pk")
            shortcode = node.get("code") or node.get("shortcode")
            caption_edges = (
                node.get("edge_media_to_caption", {}).get("edges", [])
                or node.get("caption", {}) if isinstance(node.get("caption"), list) else []
            )
            caption = ""
            if caption_edges:
                caption = caption_edges[0].get("node", {}).get("text", "")
            elif isinstance(node.get("caption"), dict):
                caption = node["caption"].get("text", "")
            elif isinstance(node.get("caption"), str):
                caption = node["caption"]

            media_type_map = {1: "image", 2: "video", 8: "carousel"}
            media_type = media_type_map.get(node.get("media_type", 1), "image")
            if node.get("product_type") == "clips":
                media_type = "reel"

            owner = node.get("owner", node.get("user", {}))

            return {
                "keyword_id": keyword_id,
                "keyword": keyword,
                "post_id": str(post_id) if post_id else None,
                "author_username": owner.get("username"),
                "caption": caption[:2000],
                "hashtags": _extract_hashtags(caption),
                "likes": _safe_int(
                    node.get("like_count")
                    or node.get("edge_liked_by", {}).get("count", 0)
                ),
                "comments": _safe_int(
                    node.get("comment_count")
                    or node.get("edge_media_to_comment", {}).get("count", 0)
                ),
                "post_type": media_type,
                "url": f"https://www.instagram.com/p/{shortcode}/" if shortcode else None,
                "posted_at": None,
            }
        except Exception as exc:
            logger.debug("[Instagram] Node parse error: %s", exc)
            return None

    async def _scrape_via_dom(
        self, page: Page, tag: str, keyword_id: str, limit: int
    ) -> list[dict]:
        """Fallback: parse post links from the hashtag page DOM."""
        results: list[dict] = []
        try:
            await human_scroll(page, scrolls=5)
            await human_delay(DELAY_MEDIUM)

            # Collect all post links visible on the page
            links = await page.eval_on_selector_all(
                "a[href*='/p/']",
                "els => els.map(e => e.href)",
            )
            seen = set()
            for link in links:
                m = re.search(r"/p/([A-Za-z0-9_-]+)/", link)
                if m:
                    shortcode = m.group(1)
                    if shortcode not in seen:
                        seen.add(shortcode)
                        results.append(
                            {
                                "keyword_id": keyword_id,
                                "keyword": tag,
                                "post_id": shortcode,
                                "author_username": None,
                                "caption": None,
                                "hashtags": [],
                                "likes": 0,
                                "comments": 0,
                                "post_type": "unknown",
                                "url": f"https://www.instagram.com/p/{shortcode}/",
                                "posted_at": None,
                            }
                        )
                if len(results) >= limit:
                    break
        except Exception as exc:
            logger.error("[Instagram] DOM fallback error: %s", exc)
        return results
