import time
from dataclasses import dataclass

from thesnow.core.database import Database


@dataclass(frozen=True)
class BonusEntry:
    """Single row from bonus_history."""

    paid_to: str
    amount: int
    reason: str
    who: str
    ts: int


@dataclass(frozen=True)
class BonusStats:
    """Aggregated bonus payouts and recent entries."""

    total_paid: int
    payout_count: int
    recent: list[BonusEntry]


async def get_bonus_stats(db: Database, guild_id: int) -> BonusStats:
    """Load total bonus payouts and recent history."""
    summary = await db.one(
        "SELECT COALESCE(SUM(amount),0) AS tot, COUNT(*) AS cnt FROM bonus_history WHERE guild_id=?",
        (guild_id,),
    )
    rows = await db.many(
        "SELECT paid_to, amount, reason, who, ts FROM bonus_history WHERE guild_id=? ORDER BY id DESC LIMIT 6",
        (guild_id,),
    )
    recent = [
        BonusEntry(
            paid_to=str(row["paid_to"]),
            amount=int(row["amount"]),
            reason=str(row["reason"] or ""),
            who=str(row["who"] or ""),
            ts=int(row["ts"]),
        )
        for row in rows
    ]
    return BonusStats(
        total_paid=int(summary["tot"]) if summary else 0,
        payout_count=int(summary["cnt"]) if summary else 0,
        recent=recent,
    )


async def record_bonus_payout(
    db: Database,
    guild_id: int,
    *,
    paid_to: str,
    amount: int,
    reason: str,
    who: str,
    now_ts: int | None = None,
) -> None:
    """Persist a bonus payout record."""
    ts = now_ts if now_ts is not None else int(time.time())
    await db.run(
        "INSERT INTO bonus_history(guild_id,paid_to,amount,reason,who,ts) VALUES(?,?,?,?,?,?)",
        (guild_id, paid_to, amount, reason, who, ts),
    )
