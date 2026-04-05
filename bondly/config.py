from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="bondly/.env", env_file_encoding="utf-8")

    # Deeds provider: "mock" | "afrigis" | "datanamix"
    deeds_provider: str = "mock"

    # AfriGIS (https://developers.afrigis.co.za)
    afrigis_client_id: str = ""
    afrigis_client_secret: str = ""

    # Datanamix (https://www.datanamix.com/developers-page/)
    datanamix_api_key: str = ""

    # Stripe
    stripe_secret_key: str = "sk_test_placeholder"
    stripe_webhook_secret: str = "whsec_placeholder"
    stripe_price_id: str = "price_placeholder"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7    # 1 week

    # App
    base_url: str = "http://localhost:8001"
    db_path: str = "./bondly/data/app.db"


@lru_cache
def get_settings() -> Settings:
    return Settings()
