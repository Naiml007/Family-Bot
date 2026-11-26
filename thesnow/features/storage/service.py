import time
from dataclasses import dataclass
from typing import Any

from thesnow.core.database import Database
from thesnow.shared.validation import Oops


@dataclass(frozen=True)
class StorageItem:
    """Record from the shared storage table."""

    item: str
    qty: int
    location: str
    last_who: str
    last_action: str
    last_img: str
    last_ts: int | None


def _coerce_ts(raw: Any) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if text.isdigit():
        return int(text)
    return None


def _row_to_item(row: Any) -> StorageItem:
    return StorageItem(
        item=str(row["item"]),
        qty=int(row["qty"]),
        location=str(row["location"] or ""),
        last_who=str(row["last_who"] or ""),
        last_action=str(row["last_action"] or ""),
        last_img=str(row["last_img"] or ""),
        last_ts=_coerce_ts(row["last_ts"]),
    )


async def get_active_storage(db: Database, guild_id: int) -> list[StorageItem]:
    """Return all positive-quantity items in shared storage."""
    rows = await db.many(
        "SELECT item, qty, location, last_who, last_action, last_img, last_ts "
        "FROM storage WHERE guild_id=? AND qty>0 ORDER BY item",
        (guild_id,),
    )
    return [_row_to_item(row) for row in rows]


async def mutate_storage(
    db: Database,
    guild_id: int,
    *,
    item: str,
    qty: int,
    mode: str,
    location: str,
    who: str,
    img_url: str,
    now_ts: int | None = None,
) -> tuple[str, int, str | None]:
    """Atomically store or take shared storage items inside BEGIN IMMEDIATE."""
    ts = now_ts if now_ts is not None else int(time.time())
    sign = 1 if mode == "add" else -1
    action_label = "Stored" if mode == "add" else "Taken"

    async with db.transaction():
        existing = await db.one(
            "SELECT item, qty, location FROM storage WHERE guild_id=? AND LOWER(item)=LOWER(?)",
            (guild_id, item),
        )
        canonical_item = str(existing["item"]) if existing else item
        have = int(existing["qty"]) if existing else 0
        prev_location = str(existing["location"] or "") if existing else None

        new_qty = have + sign * qty
        if new_qty < 0:
            raise Oops(f"Only {have} × {canonical_item} in storage.")

        await db.run(
            """
            INSERT INTO storage(guild_id, item, qty, location, last_who, last_action, last_img, last_ts)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(guild_id,item) DO UPDATE SET
              qty=excluded.qty,
              location=excluded.location,
              last_who=excluded.last_who,
              last_action=excluded.last_action,
              last_img=excluded.last_img,
              last_ts=excluded.last_ts
            """,
            (guild_id, canonical_item, new_qty, location, who, action_label, img_url, ts),
        )
        changed_from = prev_location if prev_location and prev_location != location and have > 0 else None
        return canonical_item, new_qty, changed_from


async def update_storage_image(db: Database, guild_id: int, item: str, image_url: str) -> None:
    """Persist the log-backed attachment URL on the storage item."""
    await db.run(
        "UPDATE storage SET last_img=? WHERE guild_id=? AND item=?",
        (image_url, guild_id, item),
    )


async def find_storage_item(db: Database, guild_id: int, query: str) -> StorageItem:
    """Find an item by exact case-insensitive match or substring fallback."""
    cleaned = query.strip()
    if not cleaned:
        raise Oops("Please enter an item name to search.")
    row = await db.one(
        "SELECT item, qty, location, last_who, last_action, last_img, last_ts "
        "FROM storage WHERE guild_id=? AND LOWER(item)=LOWER(?)",
        (guild_id, cleaned),
    )
    if row is None:
        row = await db.one(
            "SELECT item, qty, location, last_who, last_action, last_img, last_ts "
            "FROM storage WHERE guild_id=? AND LOWER(item) LIKE LOWER(?) "
            "ORDER BY COALESCE(last_ts, 0) DESC LIMIT 1",
            (guild_id, f"%{cleaned}%"),
        )
    if row is None:
        raise Oops(f"No item matching `{cleaned}` found in storage history.")
    return _row_to_item(row)
