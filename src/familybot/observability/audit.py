"""Audit log writer helper used by service-layer state mutations."""

from __future__ import annotations

from collections.abc import Mapping

import structlog

from familybot.core.logging import get_correlation_id
from familybot.core.permissions import ActorContext
from familybot.db.repositories.protocols import AuditLogRecord, UnitOfWork

log = structlog.get_logger()


async def record_audit(
    uow: UnitOfWork,
    actor: ActorContext,
    *,
    action: str,
    entity: str,
    entity_id: str,
    payload: Mapping[str, object] | None = None,
) -> AuditLogRecord:
    """Append an audit_log row and emit a structured INFO log entry."""
    cid = actor.correlation_id or get_correlation_id() or "unknown"
    safe_payload = dict(payload) if payload is not None else {}

    record = await uow.audit_logs.append(
        guild_id=actor.guild_id,
        actor_id=actor.discord_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        payload=safe_payload,
        correlation_id=cid,
    )
    log.info(
        "audit.recorded",
        guild_id=actor.guild_id,
        actor_id=actor.discord_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        correlation_id=cid,
    )
    return record
