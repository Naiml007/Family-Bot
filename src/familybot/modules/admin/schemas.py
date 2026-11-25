"""Plain-Python DTOs and runtime probe protocol for the admin module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    """Bot process metrics supplied by the runtime host."""

    uptime_seconds: float
    ws_latency_ms: float | None
    loaded_modules: tuple[str, ...]
    version: str
    git_sha: str | None


class RuntimeProbe(Protocol):
    """Protocol decoupling AdminService from discord.py Bot internals."""

    def get_runtime_snapshot(self) -> RuntimeSnapshot: ...

    async def ping_database(self) -> float | None: ...


@dataclass(frozen=True, slots=True)
class BotStatusDTO:
    """Status summary returned by AdminService.get_status."""

    uptime_seconds: float
    ws_latency_ms: float | None
    db_latency_ms: float | None
    pending_reminders: int | None
    failed_reminders: int | None
    loaded_modules: tuple[str, ...]
    version: str
    git_sha: str | None


@dataclass(frozen=True, slots=True)
class GuildConfigDTO:
    """Guild configuration summary."""

    guild_id: int
    timezone: str
    log_channel_id: int | None
    error_channel_id: int | None
    role_map: dict[str, int | list[int]]
    enabled_modules: dict[str, bool]
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AuditEntryDTO:
    """Audit log entry DTO for debug and recent log queries."""

    id: int
    actor_id: int
    action: str
    entity: str
    entity_id: str
    payload: dict[str, object]
    correlation_id: str
    created_at: datetime
