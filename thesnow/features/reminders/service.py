import logging
import time
from dataclasses import dataclass

import discord

from thesnow.core.context import AppContext
from thesnow.core.database import Database
from thesnow.core.errors import send_role_ping
from thesnow.shared.validation import Oops

logger = logging.getLogger("thesnow.reminders")


@dataclass(frozen=True)
class ReminderRecord:
    """Repeating reminder database row."""

    reminder_id: int
    guild_id: int
    chapter: str
    channel_id: int
    role_id: int
    message: str
    interval_min: int
    next_run: int


async def add_reminder(
    db: Database,
    guild_id: int,
    *,
    chapter: str,
    channel_id: int,
    role_id: int,
    message: str,
    interval_min: int,
    next_run: int,
) -> int:
    """Insert a repeating reminder and return its new ID."""
    safe_interval = max(1, interval_min)
    return await db.insert(
        "INSERT INTO reminders(guild_id,chapter,channel_id,role_id,message,interval_min,next_run) "
        "VALUES(?,?,?,?,?,?,?)",
        (guild_id, chapter, channel_id, role_id, message, safe_interval, next_run),
    )


async def list_reminders(db: Database, guild_id: int) -> list[ReminderRecord]:
    """List repeating reminders for a guild."""
    rows = await db.many(
        "SELECT id, guild_id, chapter, channel_id, role_id, message, interval_min, next_run "
        "FROM reminders WHERE guild_id=? ORDER BY chapter, id",
        (guild_id,),
    )
    return [
        ReminderRecord(
            reminder_id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            chapter=str(row["chapter"]),
            channel_id=int(row["channel_id"]),
            role_id=int(row["role_id"]),
            message=str(row["message"]),
            interval_min=int(row["interval_min"]),
            next_run=int(row["next_run"]),
        )
        for row in rows
    ]


async def delete_reminder(db: Database, guild_id: int, reminder_id: int) -> None:
    """Delete a reminder by ID or raise Oops if it does not exist."""
    deleted = await db.run("DELETE FROM reminders WHERE id=? AND guild_id=?", (reminder_id, guild_id))
    if deleted == 0:
        raise Oops(f"Reminder #{reminder_id} was not found in this server.")


async def setup_diplomacy(
    db: Database,
    guild_id: int,
    *,
    channel_id: int,
    role_id: int,
    now_ts: int | None = None,
) -> int:
    """Replace any existing 7-day Diplomacy reminder and return next run timestamp."""
    ts = now_ts if now_ts is not None else int(time.time())
    nxt = ts + 7 * 86400
    async with db.transaction():
        await db.run("DELETE FROM reminders WHERE guild_id=? AND chapter='Diplomacy'", (guild_id,))
        await db.run(
            "INSERT INTO reminders(guild_id,chapter,channel_id,role_id,message,interval_min,next_run) "
            "VALUES(?,?,?,?,?,?,?)",
            (guild_id, "Diplomacy", channel_id, role_id, "🤝 **Diplomacy** is ready to be taken!", 7 * 24 * 60, nxt),
        )
    return nxt


async def reset_diplomacy(db: Database, guild_id: int, *, now_ts: int | None = None) -> int:
    """Reset the 7-day Diplomacy timer or raise Oops if not configured."""
    ts = now_ts if now_ts is not None else int(time.time())
    nxt = ts + 7 * 86400
    updated = await db.run(
        "UPDATE reminders SET next_run=? WHERE guild_id=? AND chapter='Diplomacy'",
        (nxt, guild_id),
    )
    if updated == 0:
        raise Oops("Diplomacy reminder has not been configured yet. Run `/diplomacy_setup` first.")
    return nxt


async def process_due_reminders(ctx: AppContext, bot: discord.Client, now_ts: int) -> None:
    """Dispatch all due repeating reminders with per-reminder fault isolation."""
    rows = await ctx.db.many(
        "SELECT id, guild_id, chapter, channel_id, role_id, message, interval_min, next_run "
        "FROM reminders WHERE next_run<=?",
        (now_ts,),
    )
    for row in rows:
        rem_id = int(row["id"])
        guild_id = int(row["guild_id"])
        channel_id = int(row["channel_id"])
        role_id = int(row["role_id"])
        message = str(row["message"])
        interval_min = max(1, int(row["interval_min"]))
        next_run = int(row["next_run"])

        step = interval_min * 60
        jumps = ((now_ts - next_run) // step) + 1
        new_next = next_run + jumps * step

        try:
            if ctx.permissions.is_guild_allowed(guild_id):
                ch = bot.get_channel(channel_id)
                if isinstance(ch, discord.TextChannel):
                    await send_role_ping(ch, f"<@&{role_id}> ⏰ {message}")
        except (discord.NotFound, discord.Forbidden):
            logger.warning(
                "Skipping unreachable reminder channel; advancing schedule",
                extra={"guild_id": guild_id, "channel_id": channel_id, "job": f"reminder:{rem_id}"},
            )
        except Exception as ex:
            logger.exception(
                "Transient error sending reminder; backing off 60s",
                exc_info=ex,
                extra={"guild_id": guild_id, "channel_id": channel_id, "job": f"reminder:{rem_id}"},
            )
            new_next = now_ts + 60

        await ctx.db.run("UPDATE reminders SET next_run=? WHERE id=?", (new_next, rem_id))
