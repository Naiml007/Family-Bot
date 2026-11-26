import asyncio
import contextvars
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

_IN_TRANSACTION: contextvars.ContextVar[bool] = contextvars.ContextVar("thesnow_in_tx", default=False)


class Database:
    """Async SQLite database facade with serialized BEGIN IMMEDIATE write transactions."""

    def __init__(self, path: str | Path = "family.db") -> None:
        self.path = Path(path)
        self._conn: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected; call connect() first")
        return self._conn

    async def connect(self) -> None:
        """Open the SQLite connection and configure WAL and concurrency pragmas."""
        if self._conn is not None:
            return
        if self.path != Path(":memory:"):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(str(self.path), isolation_level=None, timeout=30.0)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.execute("PRAGMA busy_timeout=5000")
        self._conn = conn

    async def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Serialize writers using an explicit BEGIN IMMEDIATE transaction."""
        if _IN_TRANSACTION.get():
            yield
            return

        async with self._write_lock:
            conn = self.connection
            token = _IN_TRANSACTION.set(True)
            await conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                await conn.rollback()
                raise
            else:
                await conn.commit()
            finally:
                _IN_TRANSACTION.reset(token)

    async def run(self, sql: str, args: Sequence[Any] = ()) -> int:
        """Execute a write statement and return affected row count."""
        async with self.transaction():
            cursor = await self.connection.execute(sql, args)
            return cursor.rowcount

    async def insert(self, sql: str, args: Sequence[Any] = ()) -> int:
        """Execute an INSERT statement and return lastrowid."""
        async with self.transaction():
            cursor = await self.connection.execute(sql, args)
            if cursor.lastrowid is None:
                raise RuntimeError("INSERT did not produce lastrowid")
            return int(cursor.lastrowid)

    async def executemany(self, sql: str, seq_of_args: Sequence[Sequence[Any]]) -> None:
        """Execute a parameterized write statement across multiple argument rows atomically."""
        async with self.transaction():
            await self.connection.executemany(sql, seq_of_args)

    async def one(self, sql: str, args: Sequence[Any] = ()) -> aiosqlite.Row | None:
        """Fetch a single row matching the query."""
        async with self.connection.execute(sql, args) as cursor:
            return await cursor.fetchone()

    async def many(self, sql: str, args: Sequence[Any] = ()) -> list[aiosqlite.Row]:
        """Fetch all rows matching the query."""
        async with self.connection.execute(sql, args) as cursor:
            rows = await cursor.fetchall()
            return list(rows)

    async def executescript(self, sql: str) -> None:
        """Execute a multi-statement SQL script inside the serialized write lock."""
        async with self._write_lock:
            await self.connection.executescript(sql)


class ConfigCache:
    """Async per-guild configuration cache backed by SQLite config table."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self._values: dict[tuple[int, str], str | None] = {}
        self._loaded_guilds: set[int] = set()

    async def preload_guild(self, guild_id: int) -> None:
        """Warm the cache for all keys belonging to guild_id in a single query."""
        if guild_id in self._loaded_guilds:
            return
        rows = await self.database.many(
            "SELECT key, value FROM config WHERE guild_id=?",
            (guild_id,),
        )
        for row in rows:
            self._values[(guild_id, str(row["key"]))] = str(row["value"])
        self._loaded_guilds.add(guild_id)

    async def get(self, guild_id: int, key: str) -> str | None:
        """Fetch a config value for (guild_id, key), preloading the guild on first access."""
        cache_key = (guild_id, key)
        if cache_key not in self._values:
            if guild_id not in self._loaded_guilds:
                await self.preload_guild(guild_id)
            if cache_key not in self._values:
                self._values[cache_key] = None
        return self._values[cache_key]

    async def get_many(self, guild_id: int, *keys: str) -> dict[str, str | None]:
        """Fetch multiple config keys for a guild with at most one DB query."""
        await self.preload_guild(guild_id)
        return {key: self._values.get((guild_id, key)) for key in keys}

    async def set(self, guild_id: int, key: str, value: Any) -> None:
        """Persist a config key to SQLite and update the in-memory cache."""
        text = str(value)
        await self.database.run(
            "INSERT INTO config VALUES(?,?,?) "
            "ON CONFLICT(guild_id,key) DO UPDATE SET value=excluded.value",
            (guild_id, key, text),
        )
        self._values[(guild_id, key)] = text

    def invalidate(self, guild_id: int, key: str) -> None:
        """Evict a single key (used if an outer transaction rolls back)."""
        self._values.pop((guild_id, key), None)

    def clear_guild(self, guild_id: int) -> None:
        """Evict all cached configuration entries when leaving a guild."""
        self._loaded_guilds.discard(guild_id)
        stale = [cache_key for cache_key in self._values if cache_key[0] == guild_id]
        for cache_key in stale:
            del self._values[cache_key]
