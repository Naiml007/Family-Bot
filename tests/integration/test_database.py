import asyncio
from pathlib import Path

import aiosqlite
import pytest

from thesnow.core.database import ConfigCache, Database
from thesnow.core.migrations import LATEST_SCHEMA_VERSION, migrate
from thesnow.features.armory.service import ensure_armory_seeded, get_armory_rows, mutate_armory
from thesnow.features.balance.service import deposit, get_balance_total, withdraw
from thesnow.features.events.service import create_event, delete_event, list_upcoming_events
from thesnow.features.finance.service import create_loan, pay_loan
from thesnow.features.reminders.service import add_reminder, delete_reminder, reset_diplomacy, setup_diplomacy
from thesnow.features.seeds.service import get_seed_stock, mutate_seed_stock
from thesnow.features.solar.service import add_batteries, get_solar_stock, sell_batteries, use_batteries
from thesnow.features.storage.service import find_storage_item, mutate_storage
from thesnow.shared.validation import Oops


async def test_database_migrates_and_caches_config(tmp_path: Path) -> None:
    database = Database(tmp_path / "family.db")
    await database.connect()
    version = await migrate(database)
    assert version == LATEST_SCHEMA_VERSION

    cache = ConfigCache(database)
    await cache.set(123, "mod_role", "456")

    assert await cache.get(123, "mod_role") == "456"
    row = await database.one(
        "SELECT value FROM config WHERE guild_id=? AND key=?",
        (123, "mod_role"),
    )
    assert row is not None
    assert row["value"] == "456"

    cache.clear_guild(123)
    assert await cache.get(123, "mod_role") == "456"
    await database.close()


async def test_legacy_migration_repairs_storage_last_ts_and_creates_backup(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    async with aiosqlite.connect(str(db_path)) as conn:
        await conn.executescript(
            """
            CREATE TABLE config(guild_id INTEGER, key TEXT, value TEXT, PRIMARY KEY(guild_id,key));
            CREATE TABLE balance_log(
              id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, kind TEXT,
              amount INTEGER, detail TEXT, who TEXT, ts INTEGER
            );
            CREATE TABLE storage(guild_id INTEGER, item TEXT, qty INTEGER, PRIMARY KEY(guild_id,item));
            ALTER TABLE storage ADD COLUMN location TEXT;
            ALTER TABLE storage ADD COLUMN last_who TEXT;
            ALTER TABLE storage ADD COLUMN last_action TEXT;
            ALTER TABLE storage ADD COLUMN last_img TEXT;
            ALTER TABLE storage ADD COLUMN last_ts TEXT;
            INSERT INTO storage VALUES(1, 'Iron', 5, 'Warehouse', 'Bob', 'Stored', '', '1732665600');
            INSERT INTO storage VALUES(1, 'Wood', 2, 'Warehouse', 'Bob', 'Stored', '', 'bad-ts');
            CREATE TABLE armory(guild_id INTEGER, weapon TEXT, qty INTEGER, ammo INTEGER, PRIMARY KEY(guild_id,weapon));
            INSERT INTO armory VALUES(1, 'Armor 1', 3, 0);
            INSERT INTO armory VALUES(1, 'Gun', 4, 20);
            """
        )
        await conn.commit()

    db = Database(db_path)
    await db.connect()
    version = await migrate(db)
    assert version == LATEST_SCHEMA_VERSION
    assert list(tmp_path.glob("legacy.db.bak-*"))

    cols = await db.many("PRAGMA table_info(storage)")
    last_ts_col = next(c for c in cols if c["name"] == "last_ts")
    assert str(last_ts_col["type"]).upper() == "INTEGER"

    iron = await find_storage_item(db, 1, "iron")
    assert iron.last_ts == 1732665600
    wood = await find_storage_item(db, 1, "wood")
    assert wood.last_ts is None

    armory_rows = await get_armory_rows(db, 1)
    assert not any(r.weapon.startswith("Armor ") for r in armory_rows)
    assert next(r for r in armory_rows if r.weapon == "Gun").qty == 4

    # Idempotent second run
    assert await migrate(db) == LATEST_SCHEMA_VERSION
    await db.close()


async def test_concurrent_transactions_prevent_overdraft_and_partial_writes(tmp_path: Path) -> None:
    db = Database(tmp_path / "atomic.db")
    await db.connect()
    await migrate(db)

    await deposit(db, 1, amount=100, source="Cow Shed", who="Alice")
    results = await asyncio.gather(
        withdraw(db, 1, amount=80, pid="1", ign="A", reason="R1"),
        withdraw(db, 1, amount=80, pid="2", ign="B", reason="R2"),
        return_exceptions=True,
    )
    successes = [r for r in results if isinstance(r, int)]
    failures = [r for r in results if isinstance(r, Oops)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert await get_balance_total(db, 1) == 20

    # Seeds concurrency
    await mutate_seed_stock(db, 1, seed="Mandarins", delta=10)
    seed_res = await asyncio.gather(
        mutate_seed_stock(db, 1, seed="Mandarins", delta=-8),
        mutate_seed_stock(db, 1, seed="Mandarins", delta=-8),
        return_exceptions=True,
    )
    assert sum(1 for r in seed_res if isinstance(r, int)) == 1
    assert (await get_seed_stock(db, 1))["Mandarins"] == 2

    # Solar concurrency
    await add_batteries(db, 1, qty=5, note="", who="A")
    solar_res = await asyncio.gather(
        use_batteries(db, 1, qty=4, desc="x", who="A"),
        sell_batteries(db, 1, qty=4, price=100, who="B"),
        return_exceptions=True,
    )
    assert sum(1 for r in solar_res if isinstance(r, int)) == 1
    assert await get_solar_stock(db, 1) == 1

    # Armory Vest + Weapon atomicity + non-destructive seeding
    await ensure_armory_seeded(db, 1)
    await mutate_armory(db, 1, weapon="Gun", mode="add", weapon_qty=2, ammo_qty=10, vest_qty=3)
    with pytest.raises(Oops, match="Vest"):
        await mutate_armory(db, 1, weapon="Gun", mode="use", weapon_qty=1, ammo_qty=0, vest_qty=99)
    await ensure_armory_seeded(db, 1)  # Must preserve existing Gun/Vest stock
    arm_rows = {r.weapon: r for r in await get_armory_rows(db, 1)}
    assert arm_rows["Gun"].qty == 2
    assert arm_rows["Vest"].qty == 3

    # Storage case normalization & atomic deduction
    name1, qty1, _ = await mutate_storage(
        db,
        1,
        item="Medkit",
        qty=5,
        mode="add",
        location="Warehouse",
        who="Bob",
        img_url="",
    )
    name2, qty2, changed = await mutate_storage(
        db,
        1,
        item="medkit",
        qty=2,
        mode="use",
        location="Vehicle (482)",
        who="Bob",
        img_url="",
    )
    assert name1 == name2 == "Medkit"
    assert qty1 == 5 and qty2 == 3
    assert changed == "Warehouse"

    # Loans overpayment prevention
    loan_id = await create_loan(db, 1, party="Alex", direction="given", amount=500, note="")
    loan_res = await asyncio.gather(
        pay_loan(db, 1, query=f"#{loan_id}", amount=400),
        pay_loan(db, 1, query="alex", amount=400),
        return_exceptions=True,
    )
    assert sum(1 for r in loan_res if isinstance(r, tuple)) == 1

    # Reminders & events rowcount checks
    with pytest.raises(Oops):
        await reset_diplomacy(db, 1)
    await setup_diplomacy(db, 1, channel_id=10, role_id=20)
    await reset_diplomacy(db, 1)
    rem_id = await add_reminder(
        db, 1, chapter="Run", channel_id=10, role_id=20, message="go", interval_min=60, next_run=100
    )
    await delete_reminder(db, 1, rem_id)
    with pytest.raises(Oops):
        await delete_reminder(db, 1, rem_id)

    ev_id = await create_event(
        db, 1, title="Meet", description="", channel_id=10, role_id=20, start_ts=9_999_999_999, remind_min=10
    )
    assert len(await list_upcoming_events(db, 1)) == 1
    await delete_event(db, 1, ev_id)
    with pytest.raises(Oops):
        await delete_event(db, 1, ev_id)

    await db.close()
