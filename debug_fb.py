"""Debug Facebook response"""
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
        
        if settings.facebook_c_user and settings.facebook_xs:
            cookies = [
                {'name':'c_user','value':settings.facebook_c_user,'domain':'.facebook.com','path':'/','secure':True,'httpOnly':True},
                {'name':'xs','value':settings.facebook_xs,'domain':'.facebook.com','path':'/','secure':True,'httpOnly':True}
            ]
            if settings.facebook_datr:
                cookies.append({'name':'datr','value':settings.facebook_datr,'domain':'.facebook.com','path':'/','secure':True,'httpOnly':True})
            await ctx.add_cookies(cookies)

        page = await ctx.new_page()
        # Add stealth script
        await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        url = "https://www.facebook.com/search/posts/?q=marketingegypt"
        print(f"Navigating to {url}...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        
        title = await page.title()
        current_url = page.url
        print(f"URL: {current_url}")
        print(f"Title: {title}")
        
        content = await page.content()
        if "login" in current_url.lower():
            print("Redirected to LOGIN page - cookies might be invalid!")
        
        if "captcha" in content.lower() or "verify" in content.lower():
            print("Bot detection / CAPTCHA detected!")
            
        # Check for post items
        # Facebook uses role='article' or div with specific data-testid
        items = await page.query_selector_all("div[role='article']")
        print(f"Found {len(items)} items via role='article'")
        
        if len(items) == 0:
            # Try alternate selector
            items = await page.query_selector_all("div[data-testid='post_message']")
            print(f"Found {len(items)} items via fallback selector")
            
        await page.screenshot(path="facebook_debug.png")
        print("Screenshot saved to facebook_debug.png")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())
