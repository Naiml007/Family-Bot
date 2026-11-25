"""In-memory fake repositories and runtime probe for unit tests (no DB, no Discord)."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from datetime import datetime

from familybot.core.time import utcnow
from familybot.db.repositories.cow_shed_state import CowShedStateRecord, SqlCowShedStateRepository
from familybot.db.repositories.protocols import (
    AuditLogRecord,
    GuildSettingsRecord,
    MemberRecord,
    UnitOfWork,
)
from familybot.modules.admin.schemas import RuntimeSnapshot


class FakeGuildSettingsRepository:
    def __init__(self, store: dict[int, GuildSettingsRecord]) -> None:
        self._store = store

    async def get(self, guild_id: int) -> GuildSettingsRecord | None:
        return self._store.get(guild_id)

    async def get_or_create(self, guild_id: int) -> GuildSettingsRecord:
        existing = self._store.get(guild_id)
        if existing is not None:
            return existing
        now = utcnow()
        created = GuildSettingsRecord(
            guild_id=guild_id,
            timezone="UTC",
            log_channel_id=None,
            error_channel_id=None,
            role_map={},
            enabled_modules={},
            reminder_config={},
            created_at=now,
            updated_at=now,
        )
        self._store[guild_id] = created
        return created

    async def update(
        self,
        guild_id: int,
        *,
        timezone: str | None = None,
        log_channel_id: int | None = None,
        clear_log_channel: bool = False,
        error_channel_id: int | None = None,
        clear_error_channel: bool = False,
        role_map: Mapping[str, int | list[int]] | None = None,
        enabled_modules: Mapping[str, bool] | None = None,
        reminder_config: Mapping[str, int] | None = None,
    ) -> GuildSettingsRecord:
        current = await self.get_or_create(guild_id)
        updated = GuildSettingsRecord(
            guild_id=guild_id,
            timezone=timezone if timezone is not None else current.timezone,
            log_channel_id=(
                None
                if clear_log_channel
                else (log_channel_id if log_channel_id is not None else current.log_channel_id)
            ),
            error_channel_id=(
                None
                if clear_error_channel
                else (
                    error_channel_id if error_channel_id is not None else current.error_channel_id
                )
            ),
            role_map=dict(role_map) if role_map is not None else dict(current.role_map),
            enabled_modules=(
                dict(enabled_modules)
                if enabled_modules is not None
                else dict(current.enabled_modules)
            ),
            reminder_config=(
                dict(reminder_config)
                if reminder_config is not None
                else dict(current.reminder_config)
            ),
            created_at=current.created_at,
            updated_at=utcnow(),
        )
        self._store[guild_id] = updated
        return updated


class FakeMemberRepository:
    def __init__(self, store: dict[tuple[int, int], MemberRecord]) -> None:
        self._store = store

    async def get_by_discord_id(self, guild_id: int, discord_id: int) -> MemberRecord | None:
        return self._store.get((guild_id, discord_id))

    async def upsert(
        self,
        guild_id: int,
        discord_id: int,
        display_name: str,
        *,
        in_game_name: str | None = None,
    ) -> MemberRecord:
        existing = self._store.get((guild_id, discord_id))
        now = utcnow()
        record = MemberRecord(
            id=existing.id if existing else len(self._store) + 1,
            guild_id=guild_id,
            discord_id=discord_id,
            display_name=display_name,
            in_game_name=(
                in_game_name
                if in_game_name is not None
                else (existing.in_game_name if existing else None)
            ),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._store[(guild_id, discord_id)] = record
        return record


class FakeCowShedStateRepository(SqlCowShedStateRepository):
    def __init__(self, store: dict[int, CowShedStateRecord]) -> None:
        self._store = store

    async def get(self, guild_id: int) -> CowShedStateRecord | None:
        return self._store.get(guild_id)

    async def get_or_create(self, guild_id: int) -> CowShedStateRecord:
        existing = self._store.get(guild_id)
        if existing is not None:
            return existing
        created = CowShedStateRecord(
            guild_id=guild_id,
            fed_at=None,
            collect_at=None,
            collect_role_id=None,
            reminders_active=False,
            last_reminder_at=None,
        )
        self._store[guild_id] = created
        return created

    async def update(
        self,
        guild_id: int,
        *,
        fed_at: datetime | None = None,
        collect_at: datetime | None = None,
        collect_role_id: int | None = None,
        reminders_active: bool | None = None,
        last_reminder_at: datetime | None = None,
    ) -> CowShedStateRecord:
        record = CowShedStateRecord(
            guild_id=guild_id,
            fed_at=fed_at,
            collect_at=collect_at,
            collect_role_id=collect_role_id,
            reminders_active=bool(reminders_active),
            last_reminder_at=last_reminder_at,
        )
        self._store[guild_id] = record
        return record


class FakeAuditLogRepository:
    def __init__(self, store: list[AuditLogRecord]) -> None:
        self._store = store

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
        record = AuditLogRecord(
            id=len(self._store) + 1,
            guild_id=guild_id,
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            payload=dict(payload),
            correlation_id=correlation_id,
            created_at=utcnow(),
        )
        self._store.append(record)
        return record

    async def find_by_correlation_id(
        self, guild_id: int, correlation_id: str
    ) -> list[AuditLogRecord]:
        return [
            r for r in self._store if r.guild_id == guild_id and r.correlation_id == correlation_id
        ]

    async def list_recent(self, guild_id: int, *, limit: int = 20) -> list[AuditLogRecord]:
        matching = [r for r in self._store if r.guild_id == guild_id]
        return list(reversed(matching))[:limit]


class FakeUnitOfWork:
    def __init__(
        self,
        guild_store: dict[int, GuildSettingsRecord],
        member_store: dict[tuple[int, int], MemberRecord],
        audit_store: list[AuditLogRecord],
        cow_shed_store: dict[int, CowShedStateRecord],
    ) -> None:
        self._guild_settings = FakeGuildSettingsRepository(guild_store)
        self._members = FakeMemberRepository(member_store)
        self._audit_logs = FakeAuditLogRepository(audit_store)
        self._cow_shed_state = FakeCowShedStateRepository(cow_shed_store)
        self.committed = False
        self.rolled_back = False

    @property
    def guild_settings(self) -> FakeGuildSettingsRepository:
        return self._guild_settings

    @property
    def members(self) -> FakeMemberRepository:
        return self._members

    @property
    def audit_logs(self) -> FakeAuditLogRepository:
        return self._audit_logs

    @property
    def cow_shed_state(self) -> FakeCowShedStateRepository:
        return self._cow_shed_state

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeUnitOfWorkFactory:
    def __init__(self) -> None:
        self.guild_store: dict[int, GuildSettingsRecord] = {}
        self.member_store: dict[tuple[int, int], MemberRecord] = {}
        self.audit_store: list[AuditLogRecord] = []
        self.cow_shed_store: dict[int, CowShedStateRecord] = {}

    @asynccontextmanager
    async def open(self) -> AsyncGenerator[UnitOfWork, None]:
        uow = FakeUnitOfWork(
            self.guild_store, self.member_store, self.audit_store, self.cow_shed_store
        )
        try:
            yield uow
        except Exception:
            await uow.rollback()
            raise


class FakeRuntimeProbe:
    def __init__(
        self,
        *,
        loaded_modules: tuple[str, ...] = ("admin", "solar"),
        db_latency_ms: float | None = 1.5,
    ) -> None:
        self.loaded_modules = loaded_modules
        self.db_latency_ms = db_latency_ms

    def get_runtime_snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            uptime_seconds=125.0,
            ws_latency_ms=42.0,
            loaded_modules=self.loaded_modules,
            version="0.1.0",
            git_sha="abc1234def",
        )

    async def ping_database(self) -> float | None:
        return self.db_latency_ms
