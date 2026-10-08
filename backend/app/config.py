"""Settings read from environment variables. See .env.example for the full list."""

from functools import lru_cache

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
    cors_origins: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
