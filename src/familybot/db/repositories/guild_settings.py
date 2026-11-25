"""SQLAlchemy repository for guild_settings."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from familybot.core.time import ensure_utc, utcnow
from familybot.db.models.guild_settings import GuildSettings
from familybot.db.repositories.protocols import GuildSettingsRecord


def _to_record(row: GuildSettings) -> GuildSettingsRecord:
    return GuildSettingsRecord(
        guild_id=row.guild_id,
        timezone=row.timezone,
        log_channel_id=row.log_channel_id,
        error_channel_id=row.error_channel_id,
        role_map=dict(row.role_map),
        enabled_modules=dict(row.enabled_modules),
        reminder_config=dict(row.reminder_config),
        created_at=ensure_utc(row.created_at),
        updated_at=ensure_utc(row.updated_at),
    )


class SqlGuildSettingsRepository:
    """SQLAlchemy-backed GuildSettingsRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, guild_id: int) -> GuildSettingsRecord | None:
        stmt = select(GuildSettings).where(GuildSettings.guild_id == guild_id)
        row = await self._session.scalar(stmt)
        return _to_record(row) if row is not None else None

    async def get_or_create(self, guild_id: int) -> GuildSettingsRecord:
        stmt = select(GuildSettings).where(GuildSettings.guild_id == guild_id)
        row = await self._session.scalar(stmt)
        if row is None:
            now = utcnow()
            row = GuildSettings(
                guild_id=guild_id,
                timezone="UTC",
                role_map={},
                enabled_modules={},
                reminder_config={},
                created_at=now,
                updated_at=now,
            )
            self._session.add(row)
            await self._session.flush()
        return _to_record(row)

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
        stmt = select(GuildSettings).where(GuildSettings.guild_id == guild_id)
        row = await self._session.scalar(stmt)
        if row is None:
            now = utcnow()
            row = GuildSettings(
                guild_id=guild_id,
                timezone="UTC",
                role_map={},
                enabled_modules={},
                reminder_config={},
                created_at=now,
                updated_at=now,
            )
            self._session.add(row)

        if timezone is not None:
            row.timezone = timezone
        if clear_log_channel:
            row.log_channel_id = None
        elif log_channel_id is not None:
            row.log_channel_id = log_channel_id
        if clear_error_channel:
            row.error_channel_id = None
        elif error_channel_id is not None:
            row.error_channel_id = error_channel_id
        if role_map is not None:
            row.role_map = dict(role_map)
        if enabled_modules is not None:
            row.enabled_modules = dict(enabled_modules)
        if reminder_config is not None:
            row.reminder_config = dict(reminder_config)

        row.updated_at = utcnow()
        await self._session.flush()
        return _to_record(row)
