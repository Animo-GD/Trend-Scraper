"""
Webhook notifier for bot detection events.
Fires a POST request to the configured webhook URL when a scraper hits a CAPTCHA or bot wall.
The human-in-the-loop can then solve it and resume.
"""
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def notify_bot_detection(
    platform: str,
    keyword: str,
    url: str,
    screenshot_b64: Optional[str] = None,
    extra: Optional[dict] = None,
) -> bool:
    """
    Send a webhook notification when bot detection is encountered.

    Returns True if webhook was sent successfully (or no webhook configured).
    """
    if not settings.bot_detection_webhook_url:
        logger.warning(
            "[%s] Bot detection on '%s' but no webhook URL configured.", platform, keyword
        )
        return False

    payload = {
        "event": "bot_detection",
        "platform": platform,
        "keyword": keyword,
        "url": url,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": f"Bot detection triggered on {platform} while scraping '{keyword}'. Human review required.",
    }
    if screenshot_b64:
        payload["screenshot_base64"] = screenshot_b64
    if extra:
        payload.update(extra)

    headers = {"Content-Type": "application/json"}

    # Add HMAC signature if secret is configured
    if settings.bot_detection_webhook_secret:
        body = json.dumps(payload, sort_keys=True)
        sig = hmac.new(
            settings.bot_detection_webhook_secret.encode(),
            body.encode() if isinstance(body, str) else body,
            hashlib.sha256,
        ).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={sig}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                settings.bot_detection_webhook_url,
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            logger.info("[%s] Webhook sent successfully (status %s).", platform, resp.status_code)
            return True
    except Exception as exc:
        logger.error("[%s] Failed to send bot detection webhook: %s", platform, exc)
        return False
