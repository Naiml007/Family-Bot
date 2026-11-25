"""SQLAlchemy repository for members."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from familybot.core.time import ensure_utc, utcnow
from familybot.db.models.members import Member
from familybot.db.repositories.protocols import MemberRecord


def _to_record(row: Member) -> MemberRecord:
    return MemberRecord(
        id=row.id,
        guild_id=row.guild_id,
        discord_id=row.discord_id,
        display_name=row.display_name,
        in_game_name=row.in_game_name,
        created_at=ensure_utc(row.created_at),
        updated_at=ensure_utc(row.updated_at),
    )


class SqlMemberRepository:
    """SQLAlchemy-backed MemberRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_discord_id(self, guild_id: int, discord_id: int) -> MemberRecord | None:
        stmt = select(Member).where(
            Member.guild_id == guild_id,
            Member.discord_id == discord_id,
        )
        row = await self._session.scalar(stmt)
        return _to_record(row) if row is not None else None

    async def upsert(
        self,
        guild_id: int,
        discord_id: int,
        display_name: str,
        *,
        in_game_name: str | None = None,
    ) -> MemberRecord:
        stmt = select(Member).where(
            Member.guild_id == guild_id,
            Member.discord_id == discord_id,
        )
        row = await self._session.scalar(stmt)
        now = utcnow()
        if row is None:
            row = Member(
                guild_id=guild_id,
                discord_id=discord_id,
                display_name=display_name,
                in_game_name=in_game_name,
                created_at=now,
                updated_at=now,
            )
            self._session.add(row)
        else:
            row.display_name = display_name
            if in_game_name is not None:
                row.in_game_name = in_game_name
            row.updated_at = now
        await self._session.flush()
        return _to_record(row)
