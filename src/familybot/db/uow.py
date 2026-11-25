"""SQLAlchemy Unit of Work implementation (one session per interaction)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from familybot.db.repositories.audit_log import SqlAuditLogRepository
from familybot.db.repositories.cow_shed_state import SqlCowShedStateRepository
from familybot.db.repositories.guild_settings import SqlGuildSettingsRepository
from familybot.db.repositories.members import SqlMemberRepository
from familybot.db.repositories.protocols import UnitOfWork


class SqlUnitOfWork:
    """Wraps a single AsyncSession and exposes repositories."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._guild_settings = SqlGuildSettingsRepository(session)
        self._members = SqlMemberRepository(session)
        self._audit_logs = SqlAuditLogRepository(session)
        self._cow_shed_state = SqlCowShedStateRepository(session)

    @property
    def guild_settings(self) -> SqlGuildSettingsRepository:
        return self._guild_settings

    @property
    def cow_shed_state(self) -> SqlCowShedStateRepository:
        return self._cow_shed_state

    @property
    def members(self) -> SqlMemberRepository:
        return self._members

    @property
    def audit_logs(self) -> SqlAuditLogRepository:
        return self._audit_logs

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


class SqlUnitOfWorkFactory:
    """Creates scoped SqlUnitOfWork instances from an async_sessionmaker."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    @asynccontextmanager
    async def open(self) -> AsyncGenerator[UnitOfWork, None]:
        async with self._session_factory() as session:
            uow = SqlUnitOfWork(session)
            try:
                yield uow
            except Exception:
                await uow.rollback()
                raise
