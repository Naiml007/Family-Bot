from thesnow.core.database import Database
from thesnow.shared.constants import SEEDS
from thesnow.shared.validation import Oops


async def get_seed_stock(db: Database, guild_id: int) -> dict[str, int]:
    """Fetch all seed quantities for a guild in a single query."""
    rows = await db.many("SELECT seed, qty FROM seeds WHERE guild_id=?", (guild_id,))
    stock = {seed: 0 for seed in SEEDS}
    for row in rows:
        name = str(row["seed"])
        if name in stock:
            stock[name] = int(row["qty"])
    return stock


async def get_single_seed_qty(db: Database, guild_id: int, seed: str) -> int:
    """Fetch quantity for one seed type."""
    row = await db.one("SELECT qty FROM seeds WHERE guild_id=? AND seed=?", (guild_id, seed))
    return int(row["qty"]) if row else 0


async def mutate_seed_stock(
    db: Database,
    guild_id: int,
    *,
    seed: str,
    delta: int,
) -> int:
    """Atomically add or subtract seed stock inside BEGIN IMMEDIATE."""
    async with db.transaction():
        row = await db.one("SELECT qty FROM seeds WHERE guild_id=? AND seed=?", (guild_id, seed))
        have = int(row["qty"]) if row else 0
        if have + delta < 0:
            raise Oops(f"Only {have} {seed} in stock.")
        await db.run(
            "INSERT INTO seeds VALUES(?,?,?) ON CONFLICT(guild_id,seed) DO UPDATE SET qty=qty+excluded.qty",
            (guild_id, seed, delta),
        )
        return have + delta
