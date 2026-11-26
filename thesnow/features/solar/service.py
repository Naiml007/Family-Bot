import time
from dataclasses import dataclass

from thesnow.core.database import ConfigCache, Database
from thesnow.shared.time import uk_day_start_ts
from thesnow.shared.validation import Oops


@dataclass(frozen=True)
class SolarEntry:
    """Single row from solar_log."""

    kind: str
    qty: int
    price: int
    detail: str
    who: str
    ts: int


@dataclass(frozen=True)
class SolarStats:
    """Aggregated solar battery stats and recent events."""

    stock: int
    added_today: int
    used_today: int
    sold_today: int
    total_revenue: int
    last_repair_ts: int | None
    recent: list[SolarEntry]


async def get_solar_stock(db: Database, guild_id: int) -> int:
    """Return current battery count for a guild."""
    row = await db.one(
        "SELECT COALESCE(SUM(CASE WHEN kind='add' THEN qty ELSE -qty END), 0) AS stock "
        "FROM solar_log WHERE guild_id=?",
        (guild_id,),
    )
    return int(row["stock"]) if row else 0


async def get_solar_stats(
    db: Database,
    config: ConfigCache,
    guild_id: int,
    *,
    now_ts: float | None = None,
) -> SolarStats:
    """Load solar stock, today's counts, total revenue, repair timestamp, and recent log entries."""
    today_start = uk_day_start_ts(now_ts)
    summary = await db.one(
        """
        SELECT
          COALESCE(SUM(CASE WHEN kind='add' THEN qty ELSE -qty END), 0) AS stock,
          COALESCE(SUM(CASE WHEN kind='add' AND ts>=? THEN qty END), 0) AS added_today,
          COALESCE(SUM(CASE WHEN kind='use' AND ts>=? THEN qty END), 0) AS used_today,
          COALESCE(SUM(CASE WHEN kind='sell' AND ts>=? THEN qty END), 0) AS sold_today,
          COALESCE(SUM(CASE WHEN kind='sell' THEN qty * price END), 0) AS total_rev
        FROM solar_log WHERE guild_id=?
        """,
        (today_start, today_start, today_start, guild_id),
    )
    rep_raw = await config.get(guild_id, "solar_last_repair")
    last_repair_ts = int(rep_raw) if rep_raw and rep_raw.isdigit() else None
    rows = await db.many(
        "SELECT kind, qty, price, detail, who, ts FROM solar_log WHERE guild_id=? ORDER BY id DESC LIMIT 5",
        (guild_id,),
    )
    recent = [
        SolarEntry(
            kind=str(row["kind"]),
            qty=int(row["qty"]),
            price=int(row["price"] or 0),
            detail=str(row["detail"] or ""),
            who=str(row["who"] or ""),
            ts=int(row["ts"]),
        )
        for row in rows
    ]
    return SolarStats(
        stock=int(summary["stock"]) if summary else 0,
        added_today=int(summary["added_today"]) if summary else 0,
        used_today=int(summary["used_today"]) if summary else 0,
        sold_today=int(summary["sold_today"]) if summary else 0,
        total_revenue=int(summary["total_rev"]) if summary else 0,
        last_repair_ts=last_repair_ts,
        recent=recent,
    )


async def add_batteries(
    db: Database,
    guild_id: int,
    *,
    qty: int,
    note: str,
    who: str,
    now_ts: int | None = None,
) -> int:
    """Record added solar batteries atomically and return new stock."""
    ts = now_ts if now_ts is not None else int(time.time())
    async with db.transaction():
        await db.run(
            "INSERT INTO solar_log(guild_id,kind,qty,detail,who,ts) VALUES(?,?,?,?,?,?)",
            (guild_id, "add", qty, note, who, ts),
        )
        return await get_solar_stock(db, guild_id)


async def use_batteries(
    db: Database,
    guild_id: int,
    *,
    qty: int,
    desc: str,
    who: str,
    now_ts: int | None = None,
) -> int:
    """Atomically verify stock and record used batteries."""
    ts = now_ts if now_ts is not None else int(time.time())
    async with db.transaction():
        stock = await get_solar_stock(db, guild_id)
        if qty > stock:
            raise Oops(f"Only {stock} batteries in stock.")
        await db.run(
            "INSERT INTO solar_log(guild_id,kind,qty,detail,who,ts) VALUES(?,?,?,?,?,?)",
            (guild_id, "use", qty, desc, who, ts),
        )
        return stock - qty


async def sell_batteries(
    db: Database,
    guild_id: int,
    *,
    qty: int,
    price: int,
    who: str,
    now_ts: int | None = None,
) -> int:
    """Atomically verify stock and record sold batteries."""
    ts = now_ts if now_ts is not None else int(time.time())
    async with db.transaction():
        stock = await get_solar_stock(db, guild_id)
        if qty > stock:
            raise Oops(f"Only {stock} batteries in stock.")
        await db.run(
            "INSERT INTO solar_log(guild_id,kind,qty,price,detail,who,ts) VALUES(?,?,?,?,?,?,?)",
            (guild_id, "sell", qty, price, f"Sold @ ${price:,}/ea", who, ts),
        )
        return stock - qty
