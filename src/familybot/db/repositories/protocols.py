"""Pure-Python DTOs and repository/UoW protocols consumed by services."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from familybot.db.repositories.cow_shed_state import CowShedStateRepository


@dataclass(frozen=True, slots=True)
class GuildSettingsRecord:
    """Plain representation of a guild_settings row."""

    guild_id: int
    timezone: str
    log_channel_id: int | None
    error_channel_id: int | None
    reminders_channel_id: int | None
    role_map: dict[str, int | list[int]]
    enabled_modules: dict[str, bool]
    reminder_config: dict[str, int]
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MemberRecord:
    """Plain representation of a members row."""

    id: int
    guild_id: int
    discord_id: int
    display_name: str
    in_game_name: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AuditLogRecord:
    """Plain representation of an audit_log row."""

    id: int
    guild_id: int
    actor_id: int
    action: str
    entity: str
    entity_id: str
    payload: dict[str, object]
    correlation_id: str
    created_at: datetime


class GuildSettingsRepository(Protocol):
    """Persistence contract for guild_settings."""

    async def get(self, guild_id: int) -> GuildSettingsRecord | None: ...

    async def get_or_create(self, guild_id: int) -> GuildSettingsRecord: ...

    async def update(
        self,
        guild_id: int,
        *,
        timezone: str | None = None,
        log_channel_id: int | None = None,
        clear_log_channel: bool = False,
        error_channel_id: int | None = None,
        clear_error_channel: bool = False,
        reminders_channel_id: int | None = None,
        clear_reminders_channel: bool = False,
        role_map: Mapping[str, int | list[int]] | None = None,
        enabled_modules: Mapping[str, bool] | None = None,
        reminder_config: Mapping[str, int] | None = None,
    ) -> GuildSettingsRecord: ...


class MemberRepository(Protocol):
    """Persistence contract for members."""

    async def get_by_discord_id(self, guild_id: int, discord_id: int) -> MemberRecord | None: ...

    async def upsert(
        self,
        guild_id: int,
        discord_id: int,
        display_name: str,
        *,
        in_game_name: str | None = None,
    ) -> MemberRecord: ...


class AuditLogRepository(Protocol):
    """Persistence contract for append-only audit_log."""

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
    ) -> AuditLogRecord: ...

    async def find_by_correlation_id(
        self, guild_id: int, correlation_id: str
    ) -> list[AuditLogRecord]: ...

    async def list_recent(self, guild_id: int, *, limit: int = 20) -> list[AuditLogRecord]: ...


class UnitOfWork(Protocol):
    """Per-interaction unit of work exposing repositories and commit/rollback."""

    @property
    def guild_settings(self) -> GuildSettingsRepository: ...

    @property
    def members(self) -> MemberRepository: ...

    @property
    def audit_logs(self) -> AuditLogRepository: ...

    @property
    def cow_shed_state(self) -> CowShedStateRepository: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class UnitOfWorkFactory(Protocol):
    """Factory creating a scoped UnitOfWork per interaction."""

    def open(self) -> AbstractAsyncContextManager[UnitOfWork]: ...
