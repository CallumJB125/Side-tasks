from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Stripe
    stripe_secret_key: str = "sk_test_placeholder"
    stripe_webhook_secret: str = "whsec_placeholder"
    stripe_price_id_basic: str = "price_basic"
    stripe_price_id_pro: str = "price_pro"

    # App
    base_url: str = "http://localhost:8000"
    db_path: str = "./data/app.db"
    scraper_refresh_hours: int = 6


@lru_cache
def get_settings() -> Settings:
    return Settings()
