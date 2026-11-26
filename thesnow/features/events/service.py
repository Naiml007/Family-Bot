import logging
from dataclasses import dataclass

import discord

from thesnow.core.context import AppContext
from thesnow.core.database import Database
from thesnow.core.errors import send_role_ping
from thesnow.shared.time import uk_str
from thesnow.shared.validation import Oops

logger = logging.getLogger("thesnow.events")


@dataclass(frozen=True)
class EventRecord:
    """Scheduled event record."""

    event_id: int
    guild_id: int
    title: str
    description: str
    channel_id: int
    role_id: int
    start_ts: int
    remind_min: int
    remind_sent: int
    start_sent: int


async def create_event(
    db: Database,
    guild_id: int,
    *,
    title: str,
    description: str,
    channel_id: int,
    role_id: int,
    start_ts: int,
    remind_min: int,
) -> int:
    """Insert a scheduled event and return its ID."""
    return await db.insert(
        "INSERT INTO events(guild_id,title,description,channel_id,role_id,start_ts,remind_min) "
        "VALUES(?,?,?,?,?,?,?)",
        (guild_id, title, description, channel_id, role_id, start_ts, remind_min),
    )


async def list_upcoming_events(db: Database, guild_id: int) -> list[EventRecord]:
    """Fetch upcoming events that have not started yet."""
    rows = await db.many(
        "SELECT id, guild_id, title, description, channel_id, role_id, start_ts, remind_min, remind_sent, start_sent "
        "FROM events WHERE guild_id=? AND start_sent=0 ORDER BY start_ts",
        (guild_id,),
    )
    return [
        EventRecord(
            event_id=int(row["id"]),
            guild_id=int(row["guild_id"]),
            title=str(row["title"]),
            description=str(row["description"] or ""),
            channel_id=int(row["channel_id"]),
            role_id=int(row["role_id"]),
            start_ts=int(row["start_ts"]),
            remind_min=int(row["remind_min"]),
            remind_sent=int(row["remind_sent"]),
            start_sent=int(row["start_sent"]),
        )
        for row in rows
    ]


async def delete_event(db: Database, guild_id: int, event_id: int) -> None:
    """Delete an event by ID or raise Oops if not found."""
    deleted = await db.run("DELETE FROM events WHERE id=? AND guild_id=?", (event_id, guild_id))
    if deleted == 0:
        raise Oops(f"Event #{event_id} was not found in this server.")


async def process_due_events(ctx: AppContext, bot: discord.Client, now_ts: int) -> None:
    """Send pre-event reminders and start announcements with per-event fault isolation."""
    rows = await ctx.db.many(
        "SELECT id, guild_id, title, channel_id, role_id, start_ts, remind_min, remind_sent "
        "FROM events WHERE start_sent=0"
    )
    for row in rows:
        event_id = int(row["id"])
        guild_id = int(row["guild_id"])
        title = str(row["title"])
        channel_id = int(row["channel_id"])
        role_id = int(row["role_id"])
        start_ts = int(row["start_ts"])
        remind_min = max(0, int(row["remind_min"]))
        remind_sent = bool(row["remind_sent"])

        is_start_due = now_ts >= start_ts
        is_remind_due = (not remind_sent) and now_ts >= start_ts - remind_min * 60
        if not is_start_due and not is_remind_due:
            continue

        try:
            if ctx.permissions.is_guild_allowed(guild_id):
                ch = bot.get_channel(channel_id)
                if isinstance(ch, discord.TextChannel):
                    if is_start_due:
                        msg_text = f"<@&{role_id}> 🎉 **{title}** is starting NOW!"
                    else:
                        mins_left = max(1, round((start_ts - now_ts) / 60))
                        msg_text = f"<@&{role_id}> ⏰ **{title}** starts in {mins_left} min ({uk_str(start_ts)} UK)!"

                    await send_role_ping(ch, msg_text)
        except (discord.NotFound, discord.Forbidden):
            logger.warning(
                "Skipping unreachable event channel; marking event sent",
                extra={"guild_id": guild_id, "channel_id": channel_id, "job": f"event:{event_id}"},
            )
        except Exception as ex:
            logger.exception(
                "Transient error sending event notification",
                exc_info=ex,
                extra={"guild_id": guild_id, "channel_id": channel_id, "job": f"event:{event_id}"},
            )
            continue

        if is_start_due:
            await ctx.db.run("UPDATE events SET start_sent=1, remind_sent=1 WHERE id=?", (event_id,))
        else:
            await ctx.db.run("UPDATE events SET remind_sent=1 WHERE id=?", (event_id,))
