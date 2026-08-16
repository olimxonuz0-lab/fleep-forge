"""
Application configuration.

Settings are loaded from environment variables (see .env.example at the repo
root). We use pydantic's BaseSettings so misconfiguration fails fast at
startup instead of surfacing as a runtime error deep in a request handler.
"""
from functools import lru_cache
from typing import List

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "FLEEP FORGE API"
    app_version: str = "0.2.0"
    environment: str = Field(default="development")
    debug: bool = Field(default=False)

    # --- Security ---
    secret_key: str = Field(..., description="Used to sign JWTs. Must be set via env in prod.")
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    algorithm: str = "HS256"

    # --- Database ---
    database_url: PostgresDsn = Field(..., description="Async SQLAlchemy DSN, e.g. postgresql+asyncpg://...")
    database_pool_size: int = 10
    database_max_overflow: int = 5

    # --- Redis ---
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")

    # --- Telegram bot integration ---
    telegram_bot_token: str = Field(default="", description="Shared with fleep-bot for webhook validation.")
    telegram_webhook_secret: str = Field(default="")

    # --- CORS ---
    cors_origins: List[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Knowledge distillation ---
    obsidian_vault_path: str = Field(default="./vault")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}, got {v!r}")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — avoids re-parsing env on every request."""
    return Settings()
