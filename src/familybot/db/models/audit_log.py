"""Append-only audit log ORM model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from familybot.core.time import utcnow
from familybot.db.base import Base

_JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class AuditLog(Base):
    """Immutable audit record created for every state mutation."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_guild_created", "guild_id", "created_at"),
        Index("ix_audit_log_correlation_id", "correlation_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(_JSONVariant, nullable=False, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
