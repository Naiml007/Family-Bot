"""SQLAlchemy repository for cow_shed_state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from familybot.core.time import ensure_utc, utcnow
from familybot.db.models.cow_shed_state import CowShedState


@dataclass(frozen=True, slots=True)
class CowShedStateRecord:
    guild_id: int
    fed_at: datetime | None
    collect_at: datetime | None


def _to_dt(value: datetime | None) -> datetime | None:
    return ensure_utc(value) if value is not None else None


class CowShedStateRepository(Protocol):
    async def get(self, guild_id: int) -> CowShedStateRecord | None: ...

    async def get_or_create(self, guild_id: int) -> CowShedStateRecord: ...

    async def update(
        self,
        guild_id: int,
        *,
        fed_at: datetime | None,
        collect_at: datetime | None,
    ) -> CowShedStateRecord: ...


class SqlCowShedStateRepository:
    """SQLAlchemy-backed CowShedStateRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, guild_id: int) -> CowShedStateRecord | None:
        row = await self._session.scalar(
            select(CowShedState).where(CowShedState.guild_id == guild_id).with_for_update()
        )
        if row is None:
            return None
        return CowShedStateRecord(
            guild_id=row.guild_id,
            fed_at=_to_dt(row.fed_at),
            collect_at=_to_dt(row.collect_at),
        )

    async def get_or_create(self, guild_id: int) -> CowShedStateRecord:
        row = await self._session.scalar(
            select(CowShedState).where(CowShedState.guild_id == guild_id).with_for_update()
        )
        if row is None:
            row = CowShedState(guild_id=guild_id, fed_at=None, collect_at=None, created_at=utcnow())
            self._session.add(row)
            await self._session.flush()
        return CowShedStateRecord(
            guild_id=row.guild_id,
            fed_at=_to_dt(row.fed_at),
            collect_at=_to_dt(row.collect_at),
        )

    async def update(
        self, guild_id: int, *, fed_at: datetime | None, collect_at: datetime | None
    ) -> CowShedStateRecord:
        row = await self._session.scalar(
            select(CowShedState).where(CowShedState.guild_id == guild_id).with_for_update()
        )
        if row is None:
            row = CowShedState(guild_id=guild_id, created_at=utcnow())
            self._session.add(row)
        row.fed_at = fed_at
        row.collect_at = collect_at
        row.updated_at = utcnow()
        await self._session.flush()
        return CowShedStateRecord(
            guild_id=row.guild_id,
            fed_at=_to_dt(row.fed_at),
            collect_at=_to_dt(row.collect_at),
        )
