from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="bondly/.env", env_file_encoding="utf-8")

    # Lightstone
    lightstone_api_key: str = "mock"              # From portal.apis.lightstone.co.za
    lightstone_base_url: str = "https://portal.apis.lightstone.co.za"
    lightstone_mock_mode: bool = True             # Set False once you have real credentials

    # Stripe
    stripe_secret_key: str = "sk_test_placeholder"
    stripe_webhook_secret: str = "whsec_placeholder"
    stripe_price_id: str = "price_placeholder"    # Single price for homeowner access

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7        # 1 week

    # App
    base_url: str = "http://localhost:8001"
    db_path: str = "./bondly/data/app.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
