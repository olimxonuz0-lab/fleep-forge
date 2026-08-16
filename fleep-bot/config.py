"""Bot configuration, loaded from environment variables."""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(..., description="Telegram Bot API token from @BotFather")
    api_base_url: str = Field(default="http://localhost:8000", description="fleep-api base URL")
    api_bot_secret: str = Field(..., description="Shared secret for /auth/telegram-link, must match fleep-api")
    redis_url: str = Field(default="redis://localhost:6379/1", description="Separate DB index from fleep-api's cache use")
    use_webhook: bool = Field(default=False)
    webhook_base_url: str = Field(default="", description="Public HTTPS URL, e.g. https://bot.fleepforge.dev")
    webhook_path: str = Field(default="/webhook")
    webhook_port: int = Field(default=8080)


def get_bot_settings() -> BotSettings:
    return BotSettings()
