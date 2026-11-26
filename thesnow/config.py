from dataclasses import dataclass
from os import getenv
from pathlib import Path


class ConfigError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Validated runtime settings loaded once at process startup."""

    discord_token: str
    guild_id: int | None
    allowed_guild_ids: frozenset[int]
    db_path: Path = Path("family.db")
    log_level: str = "INFO"
    schedule_grace_seconds: int = 900


def load_settings() -> Settings:
    """Load and validate environment settings for the bot process."""
    token = (getenv("DISCORD_TOKEN") or "").strip()
    if not token:
        raise ConfigError("DISCORD_TOKEN is required")

    guild_id_text = (getenv("GUILD_ID") or "").strip()
    try:
        guild_id = int(guild_id_text) if guild_id_text else None
        allowed_guild_ids = frozenset(
            int(guild_id.strip())
            for guild_id in (getenv("ALLOWED_GUILD_IDS") or "").split(",")
            if guild_id.strip()
        )
    except ValueError as ex:
        raise ConfigError("GUILD_ID and ALLOWED_GUILD_IDS must contain integer guild IDs") from ex

    db_path_text = (getenv("DB_PATH") or "family.db").strip()
    log_level = (getenv("LOG_LEVEL") or "INFO").strip().upper() or "INFO"

    grace_text = (getenv("SCHEDULE_GRACE_SECONDS") or "900").strip()
    try:
        schedule_grace_seconds = int(grace_text)
    except ValueError as ex:
        raise ConfigError("SCHEDULE_GRACE_SECONDS must be a non-negative integer") from ex
    if schedule_grace_seconds < 0:
        raise ConfigError("SCHEDULE_GRACE_SECONDS must be a non-negative integer")

    return Settings(
        discord_token=token,
        guild_id=guild_id,
        allowed_guild_ids=allowed_guild_ids,
        db_path=Path(db_path_text),
        log_level=log_level,
        schedule_grace_seconds=schedule_grace_seconds,
    )
