from dataclasses import dataclass

from thesnow.core.database import Database
from thesnow.shared.constants import DEFAULT_ARMORY
from thesnow.shared.validation import Oops


@dataclass(frozen=True)
class ArmoryRow:
    """Single item row from the guild armory."""

    weapon: str
    qty: int
    ammo: int


async def ensure_armory_seeded(db: Database, guild_id: int) -> None:
    """Seed missing default armory weapons for a guild without overwriting existing stock."""
    async with db.transaction():
        await db.executemany(
            "INSERT OR IGNORE INTO armory(guild_id, weapon, qty, ammo) VALUES(?,?,?,?)",
            [(guild_id, weapon, qty, ammo) for weapon, qty, ammo in DEFAULT_ARMORY],
        )


async def get_armory_rows(db: Database, guild_id: int) -> list[ArmoryRow]:
    """Fetch armory inventory, seeding default rows only if the guild has none yet."""
    rows = await db.many(
        "SELECT weapon, qty, ammo FROM armory WHERE guild_id=? ORDER BY weapon",
        (guild_id,),
    )
    if not rows:
        await ensure_armory_seeded(db, guild_id)
        rows = await db.many(
            "SELECT weapon, qty, ammo FROM armory WHERE guild_id=? ORDER BY weapon",
            (guild_id,),
        )
    return [
        ArmoryRow(weapon=str(row["weapon"]), qty=int(row["qty"]), ammo=int(row["ammo"]))
        for row in rows
    ]


async def get_weapon_names(db: Database, guild_id: int) -> list[str]:
    """Return sorted non-Vest weapon names available for selection."""
    rows = await get_armory_rows(db, guild_id)
    return [row.weapon for row in rows if row.weapon != "Vest"]


async def mutate_armory(
    db: Database,
    guild_id: int,
    *,
    weapon: str,
    mode: str,
    weapon_qty: int,
    ammo_qty: int,
    vest_qty: int,
) -> None:
    """Atomically validate and apply weapon, ammo, and vest stock changes in one transaction."""
    if weapon_qty == 0 and ammo_qty == 0 and vest_qty == 0:
        raise Oops("Enter at least 1 weapon, ammo, or vest.")

    sign = 1 if mode == "add" else -1
    async with db.transaction():
        await db.executemany(
            "INSERT OR IGNORE INTO armory(guild_id, weapon, qty, ammo) VALUES(?,?,?,?)",
            [(guild_id, w, q, a) for w, q, a in DEFAULT_ARMORY],
        )
        w_row = await db.one(
            "SELECT qty, ammo FROM armory WHERE guild_id=? AND weapon=?",
            (guild_id, weapon),
        )
        have_w = int(w_row["qty"]) if w_row else 0
        have_a = int(w_row["ammo"]) if w_row else 0
        if have_w + sign * weapon_qty < 0 or have_a + sign * ammo_qty < 0:
            raise Oops(f"Not enough stock for {weapon} (Have: {have_w} pcs, {have_a} ammo).")

        if vest_qty > 0:
            v_row = await db.one(
                "SELECT qty FROM armory WHERE guild_id=? AND weapon='Vest'",
                (guild_id,),
            )
            have_v = int(v_row["qty"]) if v_row else 0
            if have_v + sign * vest_qty < 0:
                raise Oops(f"Not enough Vest in stock (Have: {have_v} pcs).")
            await db.run(
                "UPDATE armory SET qty=qty+? WHERE guild_id=? AND weapon='Vest'",
                (sign * vest_qty, guild_id),
            )

        await db.run(
            "UPDATE armory SET qty=qty+?, ammo=ammo+? WHERE guild_id=? AND weapon=?",
            (sign * weapon_qty, sign * ammo_qty, guild_id, weapon),
        )
