import time
from dataclasses import dataclass

from thesnow.core.database import Database
from thesnow.shared.validation import Oops


@dataclass(frozen=True)
class BalanceEntry:
    """Single ledger entry from balance_log."""

    entry_id: int
    kind: str
    amount: int
    detail: str
    who: str
    ts: int
    pid: str | None


@dataclass(frozen=True)
class BalanceStats:
    """Aggregated balance summary plus recent entries."""

    total_in: int
    total_out: int
    cow_shed: int
    plantation: int
    tx_count: int
    recent: list[BalanceEntry]

    @property
    def balance(self) -> int:
        return self.total_in - self.total_out

    @property
    def other(self) -> int:
        return self.total_in - self.cow_shed - self.plantation


async def get_balance_total(db: Database, guild_id: int) -> int:
    """Fetch the current available guild balance."""
    row = await db.one(
        "SELECT COALESCE(SUM(CASE WHEN kind='add' THEN amount ELSE -amount END), 0) AS t "
        "FROM balance_log WHERE guild_id=?",
        (guild_id,),
    )
    return int(row["t"]) if row else 0


async def get_balance_stats(db: Database, guild_id: int, *, recent_limit: int = 5) -> BalanceStats:
    """Fetch aggregated balance metrics and recent transactions."""
    summary = await db.one(
        """
        SELECT
          COALESCE(SUM(CASE WHEN kind='add' THEN amount END), 0) AS inc,
          COALESCE(SUM(CASE WHEN kind='wd' THEN amount END), 0) AS outc,
          COALESCE(SUM(CASE WHEN kind='add' AND detail='Cow Shed' THEN amount END), 0) AS cow,
          COALESCE(SUM(CASE WHEN kind='add' AND detail='Plantation' THEN amount END), 0) AS plant,
          COUNT(*) AS n
        FROM balance_log WHERE guild_id=?
        """,
        (guild_id,),
    )
    recent_rows = await db.many(
        "SELECT id, kind, amount, detail, who, ts, pid FROM balance_log WHERE guild_id=? ORDER BY id DESC LIMIT ?",
        (guild_id, recent_limit),
    )
    entries = [
        BalanceEntry(
            entry_id=int(row["id"]),
            kind=str(row["kind"]),
            amount=int(row["amount"]),
            detail=str(row["detail"] or ""),
            who=str(row["who"] or ""),
            ts=int(row["ts"]),
            pid=str(row["pid"]) if row["pid"] is not None else None,
        )
        for row in recent_rows
    ]
    return BalanceStats(
        total_in=int(summary["inc"]) if summary else 0,
        total_out=int(summary["outc"]) if summary else 0,
        cow_shed=int(summary["cow"]) if summary else 0,
        plantation=int(summary["plant"]) if summary else 0,
        tx_count=int(summary["n"]) if summary else 0,
        recent=entries,
    )


async def deposit(
    db: Database,
    guild_id: int,
    *,
    amount: int,
    source: str,
    who: str,
    now_ts: int | None = None,
) -> int:
    """Record a deposit inside an atomic transaction and return the updated balance."""
    ts = now_ts if now_ts is not None else int(time.time())
    async with db.transaction():
        await db.run(
            "INSERT INTO balance_log(guild_id,kind,amount,detail,who,ts) VALUES(?,?,?,?,?,?)",
            (guild_id, "add", amount, source, who, ts),
        )
        return await get_balance_total(db, guild_id)


async def withdraw(
    db: Database,
    guild_id: int,
    *,
    amount: int,
    pid: str,
    ign: str,
    reason: str,
    now_ts: int | None = None,
) -> int:
    """Atomically verify funds and record a withdrawal inside BEGIN IMMEDIATE."""
    ts = now_ts if now_ts is not None else int(time.time())
    async with db.transaction():
        available = await get_balance_total(db, guild_id)
        if amount > available:
            raise Oops("Not enough money in the family balance.")
        await db.run(
            "INSERT INTO balance_log(guild_id,kind,amount,detail,who,ts,pid) VALUES(?,?,?,?,?,?,?)",
            (guild_id, "wd", amount, reason, ign, ts, pid),
        )
        return available - amount
