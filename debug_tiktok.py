"""Debug TikTok response"""
import asyncio
import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Add root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import settings
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox','--disable-blink-features=AutomationControlled'])
        ctx = await browser.new_context(viewport={'width':1366,'height':768}, user_agent=settings.x_user_agent)
        
        if settings.tiktok_session_id:
            await ctx.add_cookies([
                {'name':'sessionid','value':settings.tiktok_session_id,'domain':'.tiktok.com','path':'/','secure':True,'httpOnly':True}
            ])

        page = await ctx.new_page()
        # Add stealth script
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        url = "https://www.tiktok.com/search?q=marketing%20egypt"
        print(f"Navigating to {url}...")
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)
        
        title = await page.title()
        current_url = page.url
        print(f"URL: {current_url}")
        print(f"Title: {title}")
        
        content = await page.content()
        if "captcha" in content.lower() or "verify" in content.lower():
            print("Bot detection / CAPTCHA detected!")
        
        # Check for search items
        items = await page.query_selector_all("[data-e2e='search_video-item']")
        print(f"Found {len(items)} search items via selector [data-e2e='search_video-item']")
        
        if len(items) == 0:
            # Try alternate selector
            items = await page.query_selector_all("div[class*='DivItemContainerV2']")
            print(f"Found {len(items)} search items via fallback selector")
            
        await page.screenshot(path="tiktok_debug.png")
        print("Screenshot saved to tiktok_debug.png")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
