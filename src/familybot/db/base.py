"""SQLAlchemy async engine, session factory, Base metadata, and DB ping."""

from __future__ import annotations

import time

from sqlalchemy import MetaData, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarative class for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def create_engine_and_sessionmaker(
    database_url: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Create an async SQLAlchemy engine and session factory."""
    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, session_factory


async def ping_db(session_factory: async_sessionmaker[AsyncSession]) -> float | None:
    """Run `SELECT 1` and return latency in milliseconds, or None on failure."""
    start = time.perf_counter()
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        return None
    return (time.perf_counter() - start) * 1000.0
