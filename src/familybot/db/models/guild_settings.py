"""Per-guild configuration ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from familybot.core.time import utcnow
from familybot.db.base import Base

_JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class GuildSettings(Base):
    """Configuration row per Discord guild (no hard-coded game/channel values)."""

    __tablename__ = "guild_settings"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    log_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reminders_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    role_map: Mapped[dict[str, int | list[int]]] = mapped_column(
        _JSONVariant, nullable=False, default=dict
    )
    enabled_modules: Mapped[dict[str, bool]] = mapped_column(
        _JSONVariant, nullable=False, default=dict
    )
    reminder_config: Mapped[dict[str, int]] = mapped_column(
        _JSONVariant, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
