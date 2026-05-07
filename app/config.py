from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Supabase (Required for data, but optional in pydantic to avoid crash-on-startup)
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # X / Twitter cookies
    x_auth_token: str = ""
    x_ct0: str = ""
    x_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    # Instagram cookies
    instagram_session_id: str = ""
    instagram_csrf_token: str = ""

    # Facebook cookies
    facebook_c_user: str = ""
    facebook_xs: str = ""
    facebook_datr: str = ""

    # TikTok cookies
    tiktok_session_id: str = ""

    # Scheduler
    scrape_interval_min_hours: float = 4.0
    scrape_interval_max_hours: float = 12.0

    # Bot detection webhook (POST to this URL when bot/CAPTCHA detected)
    bot_detection_webhook_url: Optional[str] = None
    bot_detection_webhook_secret: Optional[str] = None

    # Proxy (optional, e.g. http://user:pass@proxy.yourdomain.com:port)
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None

    # API security (optional bearer token to protect endpoints)
    api_secret_key: Optional[str] = None


settings = Settings()
