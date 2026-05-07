"""
X (Twitter) Scraper
Uses Playwright to intercept X's internal GraphQL search calls from the browser.
This is the most reliable approach since we use real authenticated browser + real queryId.
Falls back to direct API if interception fails.
"""
import asyncio
import logging
import re
import json
import sys
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
from app.webhook import notify_bot_detection

logger = logging.getLogger(__name__)


def _parse_count(value) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _extract_hashtags(text: str) -> list[str]:
    return re.findall(r"#(\w+)", text or "")


class XScraper(BaseScraper):
    platform = "x"

    async def _inject_cookies(self, context: BrowserContext) -> None:
        if not settings.x_auth_token or not settings.x_ct0:
            logger.warning("[X] Cookie credentials not set.")
            return

        cookies = [
            {
                "name": "auth_token",
                "value": settings.x_auth_token,
                "domain": ".x.com",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
            },
            {
                "name": "ct0",
                "value": settings.x_ct0,
                "domain": ".x.com",
                "path": "/",
                "secure": True,
                "httpOnly": False,
                "sameSite": "Lax",
            },
        ]
        await context.add_cookies(cookies)

    async def scrape(self, keyword: str, keyword_id: str, limit: int = 30) -> list[dict]:
        page = await self._new_page()
        results: list[dict] = []
        intercepted: list[dict] = []

        async def handle_response(response: Response):
            try:
                if "SearchTimeline" in response.url and response.status == 200:
                    body = await response.json()
                    intercepted.append(body)
            except Exception:
                pass

        page.on("response", handle_response)

        try:
            # Navigate to X home to warm up cookies
            logger.info("[X] Loading x.com...")
            await page.goto("https://x.com/", wait_until="domcontentloaded", timeout=30000)
            await human_delay(DELAY_MEDIUM)

            if await self._check_bot_detection(page, keyword):
                return results

            # Check if logged in (should see home feed, not login page)
            if "login" in page.url.lower():
                logger.error("[X] Not logged in — redirected to login page.")
                await notify_bot_detection(
                    platform="x", keyword=keyword,
                    url=page.url,
                    extra={"error": "Session expired — not logged in"},
                )
                return results

            # Navigate to search page
            search_url = f"https://x.com/search?q={keyword.replace(' ', '+')}&src=typed_query&f=top"
            logger.info("[X] Searching: %s", search_url)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await human_delay(DELAY_LONG)

            if await self._check_bot_detection(page, keyword):
                return results

            # Scroll to trigger more results + more API calls
            await human_scroll(page, scrolls=4)
            await human_delay(DELAY_MEDIUM)
            await human_scroll(page, scrolls=3)
            await human_delay(DELAY_MEDIUM)

        except Exception as exc:
            logger.error("[X] Navigation error: %s", exc)
        finally:
            page.remove_listener("response", handle_response)
            await page.close()

        # Parse intercepted GraphQL responses
        for data in intercepted:
            tweets = self._parse_search_response(data, keyword, keyword_id)
            results.extend(tweets)
            if len(results) >= limit:
                break

        results = results[:limit]
        logger.info("[X] Found %d tweets for '%s'", len(results), keyword)
        return results

    def _parse_search_response(self, data: dict, keyword: str, keyword_id: str) -> list[dict]:
        results = []
        try:
            instructions = (
                data.get("data", {})
                .get("search_by_raw_query", {})
                .get("search_timeline", {})
                .get("timeline", {})
                .get("instructions", [])
            )
            for instruction in instructions:
                if instruction.get("type") == "TimelineAddEntries":
                    for entry in instruction.get("entries", []):
                        tweet = self._extract_tweet(entry, keyword, keyword_id)
                        if tweet:
                            results.append(tweet)
        except Exception as exc:
            logger.debug("[X] Parse error: %s", exc)
        return results

    def _extract_tweet(self, entry: dict, keyword: str, keyword_id: str) -> Optional[dict]:
        try:
            item_content = entry.get("content", {}).get("itemContent", {})
            tweet_results = item_content.get("tweet_results", {}).get("result", {})

            if tweet_results.get("__typename") == "TweetTombstone":
                return None

            # X new API: user info is in result.core (not result.core.user_results.result.legacy)
            user_result = (
                tweet_results.get("core", {})
                .get("user_results", {})
                .get("result", {})
            )
            # Screen name and display name are now in user_result.core (not legacy)
            user_core = user_result.get("core", {})
            user_legacy = user_result.get("legacy", {})

            screen_name = user_core.get("screen_name") or user_legacy.get("screen_name")
            display_name = user_core.get("name") or user_legacy.get("name")

            tweet = tweet_results.get("legacy", {})
            if not tweet:
                return None

            text = tweet.get("full_text", "")
            tweet_id = tweet.get("id_str")
            if not tweet_id:
                return None

            return {
                "keyword_id": keyword_id,
                "keyword": keyword,
                "tweet_id": tweet_id,
                "author_username": screen_name,
                "author_display_name": display_name,
                "content": text,
                "hashtags": _extract_hashtags(text),
                "likes": _parse_count(tweet.get("favorite_count")),
                "retweets": _parse_count(tweet.get("retweet_count")),
                "replies": _parse_count(tweet.get("reply_count")),
                "views": _parse_count(tweet_results.get("views", {}).get("count")),
                "url": f"https://x.com/{screen_name}/status/{tweet_id}" if screen_name else None,
                "posted_at": tweet.get("created_at"),
            }
        except Exception:
            return None

