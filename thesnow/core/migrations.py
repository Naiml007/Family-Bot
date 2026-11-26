import logging
import shutil
import time
from pathlib import Path

from .database import Database

logger = logging.getLogger("thesnow.migrations")

LATEST_SCHEMA_VERSION = 2

_BASELINE_DDL = """
CREATE TABLE IF NOT EXISTS config(
  guild_id INTEGER, key TEXT, value TEXT, PRIMARY KEY(guild_id,key)
);
CREATE TABLE IF NOT EXISTS reminders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, chapter TEXT,
  channel_id INTEGER, role_id INTEGER, message TEXT, interval_min INTEGER,
  next_run INTEGER
);
CREATE TABLE IF NOT EXISTS balance_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, kind TEXT,
  amount INTEGER, detail TEXT, who TEXT, ts INTEGER, pid TEXT
);
CREATE TABLE IF NOT EXISTS seeds(
  guild_id INTEGER, seed TEXT, qty INTEGER, PRIMARY KEY(guild_id,seed)
);
CREATE TABLE IF NOT EXISTS armory(
  guild_id INTEGER, weapon TEXT, qty INTEGER, ammo INTEGER,
  PRIMARY KEY(guild_id,weapon)
);
CREATE TABLE IF NOT EXISTS storage(
  guild_id INTEGER, item TEXT, qty INTEGER, location TEXT, last_who TEXT,
  last_action TEXT, last_img TEXT, last_ts INTEGER,
  PRIMARY KEY(guild_id,item)
);
CREATE TABLE IF NOT EXISTS loans(
  id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, party TEXT,
  direction TEXT, total INTEGER, paid INTEGER DEFAULT 0, note TEXT
);
CREATE TABLE IF NOT EXISTS solar_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, kind TEXT,
  qty INTEGER, price INTEGER DEFAULT 0, detail TEXT, who TEXT, ts INTEGER
);
CREATE TABLE IF NOT EXISTS bonus_history(
  id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, paid_to TEXT,
  amount INTEGER, reason TEXT, who TEXT, ts INTEGER
);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, title TEXT,
  description TEXT, channel_id INTEGER, role_id INTEGER, start_ts INTEGER,
  remind_min INTEGER, remind_sent INTEGER DEFAULT 0,
  start_sent INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS active_alerts(
  guild_id INTEGER, kind TEXT, slot_key TEXT, channel_id INTEGER,
  msg_id INTEGER, last_ping INTEGER, ack INTEGER DEFAULT 0,
  PRIMARY KEY(guild_id, kind)
);
CREATE INDEX IF NOT EXISTS ix_reminders_due ON reminders(next_run);
CREATE INDEX IF NOT EXISTS ix_events_pending ON events(start_sent, start_ts);
CREATE INDEX IF NOT EXISTS ix_balance_guild ON balance_log(guild_id, id DESC);
CREATE INDEX IF NOT EXISTS ix_alerts_ack ON active_alerts(guild_id, ack);
CREATE INDEX IF NOT EXISTS ix_solar_guild_ts ON solar_log(guild_id, ts);
CREATE INDEX IF NOT EXISTS ix_loans_active ON loans(guild_id, id) WHERE paid < total;
"""


async def _get_user_version(database: Database) -> int:
    row = await database.one("PRAGMA user_version")
    return int(row[0]) if row else 0


async def _set_user_version(database: Database, version: int) -> None:
    await database.connection.execute(f"PRAGMA user_version = {int(version)}")


def _backup_database_if_needed(db_path: Path, current_version: int) -> None:
    if current_version >= LATEST_SCHEMA_VERSION:
        return
    if db_path == Path(":memory:") or not db_path.exists() or db_path.stat().st_size == 0:
        return
    backup_path = db_path.with_name(f"{db_path.name}.bak-{int(time.time())}")
    shutil.copy2(db_path, backup_path)
    logger.info("Created pre-migration database backup at %s", backup_path)


async def _migrate_v1(database: Database) -> None:
    await database.executescript(_BASELINE_DDL)

    balance_cols = {
        str(row["name"])
        for row in await database.many("PRAGMA table_info(balance_log)")
    }
    if "pid" not in balance_cols:
        await database.run("ALTER TABLE balance_log ADD COLUMN pid TEXT")

    storage_cols = {
        str(row["name"])
        for row in await database.many("PRAGMA table_info(storage)")
    }
    for column, col_type in (
        ("location", "TEXT"),
        ("last_who", "TEXT"),
        ("last_action", "TEXT"),
        ("last_img", "TEXT"),
        ("last_ts", "INTEGER"),
    ):
        if column not in storage_cols:
            await database.run(f"ALTER TABLE storage ADD COLUMN {column} {col_type}")


async def _migrate_v2(database: Database) -> None:
    storage_info = await database.many("PRAGMA table_info(storage)")
    last_ts_col = next((row for row in storage_info if str(row["name"]) == "last_ts"), None)
    if last_ts_col is not None and str(last_ts_col["type"]).upper() != "INTEGER":
        logger.info("Rebuilding storage table to coerce legacy last_ts column to INTEGER")
        async with database.transaction():
            await database.connection.execute(
                """
                CREATE TABLE storage_new(
                  guild_id INTEGER, item TEXT, qty INTEGER, location TEXT, last_who TEXT,
                  last_action TEXT, last_img TEXT, last_ts INTEGER,
                  PRIMARY KEY(guild_id,item)
                )
                """
            )
            await database.connection.execute(
                """
                INSERT INTO storage_new(guild_id, item, qty, location, last_who, last_action, last_img, last_ts)
                SELECT
                  guild_id,
                  item,
                  qty,
                  location,
                  last_who,
                  last_action,
                  last_img,
                  CASE
                    WHEN last_ts IS NULL THEN NULL
                    WHEN typeof(last_ts) = 'integer' THEN last_ts
                    WHEN typeof(last_ts) = 'real' THEN CAST(last_ts AS INTEGER)
                    WHEN trim(CAST(last_ts AS TEXT)) GLOB '[0-9]*'
                         AND length(trim(CAST(last_ts AS TEXT))) > 0
                      THEN CAST(trim(CAST(last_ts AS TEXT)) AS INTEGER)
                    ELSE NULL
                  END
                FROM storage
                """
            )
            await database.connection.execute("DROP TABLE storage")
            await database.connection.execute("ALTER TABLE storage_new RENAME TO storage")

    # Clean legacy Armor 1/2/3 rows once during migration rather than on every render.
    await database.run("DELETE FROM armory WHERE weapon LIKE 'Armor %'")


async def migrate(database: Database) -> int:
    """Apply ordered, idempotent forward migrations tracked via PRAGMA user_version."""
    version = await _get_user_version(database)
    _backup_database_if_needed(database.path, version)

    if version < 1:
        await _migrate_v1(database)
        await _set_user_version(database, 1)
        version = 1

    if version < 2:
        await _migrate_v2(database)
        await _set_user_version(database, 2)
        version = 2

    return version
