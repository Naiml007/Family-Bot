"""Shared pytest fixtures."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from familybot.core.config import Settings
from familybot.db.base import Base, create_engine_and_sessionmaker
from familybot.db.uow import SqlUnitOfWorkFactory


@pytest.fixture
async def pg_session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Provide a real PostgreSQL async_sessionmaker for integration tests."""
    explicit_url = os.getenv("TEST_DATABASE_URL")
    if not explicit_url and not (os.getenv("CI") or os.getenv("REQUIRE_DB_TESTS") == "1"):
        pytest.skip("Set TEST_DATABASE_URL or REQUIRE_DB_TESTS=1 to run DB integration tests.")
    db_url = explicit_url
    if db_url is None:
        settings = Settings()
        if settings.DATABASE_URL is None:
            pytest.skip("Set DATABASE_URL or TEST_DATABASE_URL to run DB integration tests.")
        db_url = settings.DATABASE_URL.get_secret_value()
    engine, session_factory = create_engine_and_sessionmaker(db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:
        await engine.dispose()
        if os.getenv("CI") or os.getenv("REQUIRE_DB_TESTS") == "1":
            raise
        pytest.skip(f"PostgreSQL is not available locally: {exc}")

    try:
        yield session_factory
    finally:
        await engine.dispose()


@pytest.fixture
async def pg_uow_factory(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> SqlUnitOfWorkFactory:
    """Provide a SqlUnitOfWorkFactory bound to a real PostgreSQL instance."""
    return SqlUnitOfWorkFactory(pg_session_factory)
