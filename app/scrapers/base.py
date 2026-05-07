"""
Abstract base class for all platform scrapers.
"""
import asyncio
import base64
import logging
import random
from abc import ABC, abstractmethod
from typing import Any, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from app.config import settings
from app.webhook import notify_bot_detection

logger = logging.getLogger(__name__)

# Inline stealth script — avoids playwright-stealth's pkg_resources bug on Python 3.12
_STEALTH_SCRIPT = """
// Remove webdriver flag
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Fake plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const arr = [{ name: 'Chrome PDF Plugin' }, { name: 'Chromium PDF Plugin' }, { name: 'Microsoft Edge PDF Plugin' }];
        arr.item = (i) => arr[i];
        arr.namedItem = (n) => arr.find(p => p.name === n);
        arr.refresh = () => {};
        return arr;
    }
});

// Fake languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// Fake hardware concurrency
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

// Chrome runtime
window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {}, app: {} };

// Permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);

// WebGL vendor spoofing
const getParam = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParam.apply(this, [parameter]);
};
"""


# Human-like timing constants
DELAY_SHORT = (0.5, 1.5)    # Between micro-interactions
DELAY_MEDIUM = (2.0, 5.0)   # Between major actions
DELAY_LONG = (5.0, 12.0)    # After page loads / before scraping


async def human_delay(range_: tuple[float, float] = DELAY_MEDIUM) -> None:
    """Sleep for a random duration to mimic human behavior."""
    await asyncio.sleep(random.uniform(*range_))


async def human_scroll(page: Page, scrolls: int = 3) -> None:
    """Scroll the page slowly like a human reading content."""
    for _ in range(scrolls):
        distance = random.randint(300, 800)
        await page.evaluate(f"window.scrollBy(0, {distance})")
        await human_delay(DELAY_SHORT)


BOT_SIGNALS = [
    "captcha",
    "challenge",
    "unusual activity",
    "verify you are human",
    "i'm not a robot",
    "access denied",
    "blocked",
    "suspicious activity",
    "security check",
    "please verify",
    "recaptcha",
    "hcaptcha",
]

# URL patterns that clearly indicate blocking/verification
BOT_URL_SIGNALS = [
    "captcha",
    "challenge",
    "verify",
    "locked",
    "suspended",
    "checkpoint",
]

# CSS selectors for known CAPTCHA widgets
BOT_SELECTORS = [
    "iframe[src*='recaptcha']",
    "iframe[src*='hcaptcha']",
    "iframe[src*='captcha']",
    "[id*='captcha']",
    "[class*='captcha']",
    "[data-testid='ocfChallengeButton']",  # Twitter challenge
    "[data-testid='LoginForm_Login_Button']",  # Login wall
    "input[name='session[username_or_email]']",  # Login form
]


class BaseScraper(ABC):
    platform: str = "base"

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    # ------------------------------------------------------------------ #
    #  Browser lifecycle                                                    #
    # ------------------------------------------------------------------ #

    async def _launch_browser(self) -> BrowserContext:
        """Launch a stealth Playwright browser with optional proxy."""
        self._playwright = await async_playwright().start()

        launch_kwargs: dict[str, Any] = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1366,768",
            ],
        }

        proxy_url = settings.https_proxy or settings.http_proxy
        if proxy_url:
            launch_kwargs["proxy"] = {"server": proxy_url}

        self._browser = await self._playwright.chromium.launch(**launch_kwargs)

        context_kwargs: dict[str, Any] = {
            "viewport": {"width": 1366, "height": 768},
            "user_agent": settings.x_user_agent,
            "locale": "en-US",
            "timezone_id": "America/New_York",
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
            },
        }

        self._context = await self._browser.new_context(**context_kwargs)

        # Inject cookies before returning context
        await self._inject_cookies(self._context)

        return self._context

    @abstractmethod
    async def _inject_cookies(self, context: BrowserContext) -> None:
        """Inject platform-specific session cookies."""
        ...

    async def _close_browser(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def _new_page(self) -> Page:
        """Open a new stealth page with inline anti-detection JS."""
        assert self._context is not None
        page = await self._context.new_page()
        # Inject stealth script before any page content loads
        await page.add_init_script(_STEALTH_SCRIPT)
        return page


    # ------------------------------------------------------------------ #
    #  Bot detection                                                        #
    # ------------------------------------------------------------------ #

    async def _check_bot_detection(self, page: Page, keyword: str) -> bool:
        """
        Inspect the page for common bot detection signals.
        Returns True if bot detection was found and webhook was fired.
        """
        url = page.url
        url_lower = url.lower()
        title_lower = (await page.title()).lower()

        # 1. URL-based detection (most reliable — URLs clearly indicate bot gates)
        url_triggered = any(sig in url_lower for sig in BOT_URL_SIGNALS)

        # 2. Title-based detection (avoid false positives from JS bundles in body)
        title_triggered = any(sig in title_lower for sig in ["captcha", "verify", "blocked", "challenge", "access denied", "suspended"])

        # 3. CSS selector detection (CAPTCHA widgets and login forms)
        selector_triggered = False
        for selector in BOT_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el:
                    selector_triggered = True
                    break
            except Exception:
                pass

        triggered = url_triggered or title_triggered or selector_triggered
        if not triggered:
            return False

        logger.warning("[%s] Bot detection on '%s' at %s", self.platform, keyword, url)

        # Capture screenshot as base64
        screenshot_b64: Optional[str] = None
        try:
            raw = await page.screenshot(type="png")
            screenshot_b64 = base64.b64encode(raw).decode()
        except Exception:
            pass

        await notify_bot_detection(
            platform=self.platform,
            keyword=keyword,
            url=url,
            screenshot_b64=screenshot_b64,
        )
        return True


    # ------------------------------------------------------------------ #
    #  Public scrape interface                                              #
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def scrape(self, keyword: str, keyword_id: str, limit: int = 30) -> list[dict]:
        """Scrape trends for the given keyword. Returns list of row dicts."""
        ...

    async def run(self, keyword: str, keyword_id: str, limit: int = 30) -> list[dict]:
        """Entry point: sets up browser, runs scrape, tears down."""
        try:
            await self._launch_browser()
            results = await self.scrape(keyword, keyword_id, limit)
            return results
        finally:
            await self._close_browser()
