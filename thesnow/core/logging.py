import logging
from typing import ClassVar

_CONTEXT_FIELDS: tuple[str, ...] = (
    "guild_id",
    "user_id",
    "channel_id",
    "action",
    "error_id",
    "job",
    "feature",
    "command",
    "custom_id",
)


class ContextFormatter(logging.Formatter):
    """Format log records while preserving structured context fields."""

    _SENSITIVE_KEYS: ClassVar[frozenset[str]] = frozenset({"token", "discord_token", "secret"})

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras: list[str] = []
        for field_name in _CONTEXT_FIELDS:
            value = getattr(record, field_name, None)
            if value is not None:
                text = "[REDACTED]" if field_name.lower() in self._SENSITIVE_KEYS else str(value)
                extras.append(f"{field_name}={text}")
        if extras:
            return f"{base} | {' '.join(extras)}"
        return base


def configure_logging(level_name: str = "INFO") -> logging.Logger:
    """Configure the application logger with structured context formatting."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logger = logging.getLogger("thesnow")
    logger.setLevel(level)

    if not logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(ContextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logger.addHandler(stream_handler)
    else:
        for existing_handler in logger.handlers:
            existing_handler.setFormatter(ContextFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    logger.propagate = False
    return logger
