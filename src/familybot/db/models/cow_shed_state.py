"""Cow Shed state per guild."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from familybot.core.time import utcnow
from familybot.db.base import Base


class CowShedState(Base):
    """Tracks when cows were fed and when milk collection is next due."""

    __tablename__ = "cow_shed_state"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    fed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collect_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collect_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reminder_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reminders_active: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    last_reminder_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True, default=utcnow
    )
