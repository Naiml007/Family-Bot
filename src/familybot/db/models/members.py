"""Family member mapping ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from familybot.core.time import utcnow
from familybot.db.base import Base


class Member(Base):
    """Links a Discord user in a guild to their in-game name."""

    __tablename__ = "members"
    __table_args__ = (
        UniqueConstraint("guild_id", "discord_id", name="uq_members_guild_discord"),
        Index("ix_members_guild_id", "guild_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discord_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    in_game_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
