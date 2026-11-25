"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed runtime settings loaded from `.env` and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    ENV: Literal["dev", "prod", "test"] = "dev"
    LOG_LEVEL: str = "INFO"

    DISCORD_TOKEN: SecretStr = Field(default=SecretStr("unset"))
    DISCORD_GUILD_ID: int | None = None

    DATABASE_URL: SecretStr = Field(
        default=SecretStr("postgresql+asyncpg://familybot:familybot@localhost:5432/familybot")
    )

    HEALTH_HOST: str = "0.0.0.0"  # noqa: S104
    HEALTH_PORT: int = 8080

    SENTRY_DSN: SecretStr | None = None
    VERSION: str = "0.1.0"
    GIT_SHA: str | None = None

    @field_validator("DISCORD_GUILD_ID", "SENTRY_DSN", "GIT_SHA", mode="before")
    @classmethod
    def _empty_str_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
