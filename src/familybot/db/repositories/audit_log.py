"""SQLAlchemy repository for append-only audit_log."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from familybot.core.time import ensure_utc, utcnow
from familybot.db.models.audit_log import AuditLog
from familybot.db.repositories.protocols import AuditLogRecord


def _to_record(row: AuditLog) -> AuditLogRecord:
    return AuditLogRecord(
        id=row.id,
        guild_id=row.guild_id,
        actor_id=row.actor_id,
        action=row.action,
        entity=row.entity,
        entity_id=row.entity_id,
        payload=dict(row.payload),
        correlation_id=row.correlation_id,
        created_at=ensure_utc(row.created_at),
    )


class SqlAuditLogRepository:
    """SQLAlchemy-backed AuditLogRepository (append-only)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        guild_id: int,
        actor_id: int,
        action: str,
        entity: str,
        entity_id: str,
        payload: Mapping[str, object],
        correlation_id: str,
    ) -> AuditLogRecord:
        row = AuditLog(
            guild_id=guild_id,
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            payload=dict(payload),
            correlation_id=correlation_id,
            created_at=utcnow(),
        )
        self._session.add(row)
        await self._session.flush()
        return _to_record(row)

    async def find_by_correlation_id(
        self, guild_id: int, correlation_id: str
    ) -> list[AuditLogRecord]:
        stmt = (
            select(AuditLog)
            .where(
                AuditLog.guild_id == guild_id,
                AuditLog.correlation_id == correlation_id,
            )
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        )
        rows = await self._session.scalars(stmt)
        return [_to_record(row) for row in rows]

    async def list_recent(self, guild_id: int, *, limit: int = 20) -> list[AuditLogRecord]:
        stmt = (
            select(AuditLog)
            .where(AuditLog.guild_id == guild_id)
            .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
            .limit(limit)
        )
        rows = await self._session.scalars(stmt)
        return [_to_record(row) for row in rows]
