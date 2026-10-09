"""Settings read from environment variables. See .env.example for the full list."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./agent_office.db"
    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_owner_user_id: int = 0
    telegram_webhook_secret: str = ""
    ingest_secret: str = ""
    strava_client_id: str = ""
    strava_client_secret: str = ""
    strava_refresh_token: str = ""
    strava_athlete_id: int = 0
    strava_webhook_verify_token: str = ""
    strava_backfill_days: int = 365
    # Base URL for OAuth/webhook callbacks. Railway sets RAILWAY_PUBLIC_DOMAIN automatically.
    public_base_url: str = ""
    railway_public_domain: str = ""
    cors_origins: str = "http://localhost:5173"

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        """Railway hands out postgres:// URLs; SQLAlchemy needs the psycopg 3 driver named."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


def public_base_url(fallback: str) -> str:
    """https://<public domain> for callbacks; ``fallback`` (the request's base URL) locally."""
    settings = get_settings()
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    if settings.railway_public_domain:
        return f"https://{settings.railway_public_domain}"
    return fallback.rstrip("/")
