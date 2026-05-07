"""
__init__.py for scrapers package
"""
from app.scrapers.x_scraper import XScraper
from app.scrapers.instagram_scraper import InstagramScraper
from app.scrapers.facebook_scraper import FacebookScraper
from app.scrapers.tiktok_scraper import TikTokScraper

__all__ = ["XScraper", "InstagramScraper", "FacebookScraper", "TikTokScraper"]
