import logging
import time
from dataclasses import dataclass

import discord

from thesnow.core.context import AppContext
from thesnow.shared.constants import GOLD, GREEN, RED
from thesnow.shared.time import (
    latest_due_cow_slot,
    latest_due_plant_slot,
    next_cow_slot,
    next_plant_slot,
    slot_label_from_key,
    uk_str,
)

logger = logging.getLogger("thesnow.schedule")

PING = discord.AllowedMentions(roles=True)


@dataclass(frozen=True)
class ActiveAlert:
    """Persisted Cow Shed or Plantation alert state."""

    guild_id: int
    kind: str
    slot_key: str
    channel_id: int
    msg_id: int
    last_ping: int
    ack: int


async def get_active_alert(db_ctx: AppContext, guild_id: int, kind: str) -> ActiveAlert | None:
    """Fetch the current alert record for a guild and schedule kind."""
    row = await db_ctx.db.one(
        "SELECT guild_id, kind, slot_key, channel_id, msg_id, last_ping, ack "
        "FROM active_alerts WHERE guild_id=? AND kind=?",
        (guild_id, kind),
    )
    if row is None:
        return None
    return ActiveAlert(
        guild_id=int(row["guild_id"]),
        kind=str(row["kind"]),
        slot_key=str(row["slot_key"]),
        channel_id=int(row["channel_id"]),
        msg_id=int(row["msg_id"]),
        last_ping=int(row["last_ping"]),
        ack=int(row["ack"]),
    )


async def get_unacked_alert_by_message(
    ctx: AppContext,
    guild_id: int,
    message_id: int,
) -> ActiveAlert | None:
    """Look up an unacknowledged alert by message ID."""
    row = await ctx.db.one(
        "SELECT guild_id, kind, slot_key, channel_id, msg_id, last_ping, ack "
        "FROM active_alerts WHERE guild_id=? AND msg_id=? AND ack=0",
        (guild_id, message_id),
    )
    if row is None:
        return None
    return ActiveAlert(
        guild_id=int(row["guild_id"]),
        kind=str(row["kind"]),
        slot_key=str(row["slot_key"]),
        channel_id=int(row["channel_id"]),
        msg_id=int(row["msg_id"]),
        last_ping=int(row["last_ping"]),
        ack=int(row["ack"]),
    )


async def acknowledge_alert(
    ctx: AppContext,
    guild: discord.Guild,
    actor_id: int,
    alert: ActiveAlert,
    *,
    now_ts: float | None = None,
) -> bool:
    """Acknowledge an active alert atomically, delete its ping message, and refresh its panel."""
    ts = now_ts if now_ts is not None else time.time()
    updated = await ctx.db.run(
        "UPDATE active_alerts SET ack=1 WHERE guild_id=? AND kind=? AND ack=0",
        (alert.guild_id, alert.kind),
    )
    if updated == 0:
        return False

    await ctx.config.set(alert.guild_id, f"{alert.kind}_last_done", f"<@{actor_id}> at **{uk_str(ts)}**")
    channel = guild.get_channel(alert.channel_id)
    if isinstance(channel, discord.TextChannel):
        try:
            await channel.get_partial_message(alert.msg_id).delete()
        except discord.HTTPException:
            pass

    await refresh_schedule_panel(ctx, guild, alert.kind)
    ctx.scheduler.notify()
    return True


async def refresh_schedule_panel(ctx: AppContext, guild: discord.Guild, kind: str) -> None:
    """Refresh the Cow Shed or Plantation panel via the coalescing PanelRegistry."""
    await ctx.panels.refresh(
        guild,
        kind,
        channel_key=f"{kind}_rem_ch",
        msg_key=f"{kind}_panel_msg",
    )


async def process_uk_schedules(
    ctx: AppContext,
    bot: discord.Client,
    now_ts: int,
    *,
    ack_view_factory: object,
) -> None:
    """Process due UK Cow Shed and Plantation slots and 5-minute alert re-pings."""
    enabled_rows = await ctx.db.many(
        "SELECT guild_id FROM config WHERE key='plantation_rem_enabled' AND value='1'"
    )
    grace = ctx.settings.schedule_grace_seconds

    for cfg_row in enabled_rows:
        gid = int(cfg_row["guild_id"])
        if not ctx.permissions.is_guild_allowed(gid):
            continue
        guild = bot.get_guild(gid)
        if guild is None:
            continue

        cfg = await ctx.config.get_many(
            gid,
            "plantation_rem_role",
            "cowshed_rem_ch",
            "plantation_rem_ch",
        )
        rid = cfg["plantation_rem_role"]
        if not rid or not rid.isdigit():
            continue
        role_ping = f"<@&{rid}>"

        triggers: list[tuple[str, str, int, str]] = []
        cow_due = latest_due_cow_slot(now_ts, grace)
        cow_ch = cfg["cowshed_rem_ch"]
        if cow_due is not None and cow_ch and cow_ch.isdigit():
            _, slot_key, hhmm = cow_due
            triggers.append(
                ("cowshed", slot_key, int(cow_ch), f"🐄 **COW FEED & MILK TIME ({hhmm} UK)**")
            )

        plant_due = latest_due_plant_slot(now_ts, grace)
        plant_ch = cfg["plantation_rem_ch"]
        if plant_due is not None and plant_ch and plant_ch.isdigit():
            _, slot_key, hhmm = plant_due
            triggers.append(
                ("plantation", slot_key, int(plant_ch), f"🌱 **PLANTATION NOURISH TIME ({hhmm} UK)**")
            )

        for kind, slot_key, ch_id, headline in triggers:
            try:
                await _trigger_slot_if_new(
                    ctx,
                    guild,
                    kind=kind,
                    slot_key=slot_key,
                    channel_id=ch_id,
                    headline=headline,
                    role_ping=role_ping,
                    now_ts=now_ts,
                    ack_view_factory=ack_view_factory,
                )
            except Exception as ex:
                logger.exception(
                    "Failed processing schedule slot trigger",
                    exc_info=ex,
                    extra={"guild_id": gid, "channel_id": ch_id, "job": f"schedule:{kind}"},
                )

        unacked = await ctx.db.many(
            "SELECT guild_id, kind, slot_key, channel_id, msg_id, last_ping, ack "
            "FROM active_alerts WHERE guild_id=? AND ack=0",
            (gid,),
        )
        for row in unacked:
            alert = ActiveAlert(
                guild_id=int(row["guild_id"]),
                kind=str(row["kind"]),
                slot_key=str(row["slot_key"]),
                channel_id=int(row["channel_id"]),
                msg_id=int(row["msg_id"]),
                last_ping=int(row["last_ping"]),
                ack=int(row["ack"]),
            )
            if now_ts - alert.last_ping < 300:
                continue
            try:
                await _reping_alert(
                    ctx,
                    guild,
                    alert=alert,
                    role_ping=role_ping,
                    now_ts=now_ts,
                    ack_view_factory=ack_view_factory,
                )
            except Exception as ex:
                logger.exception(
                    "Failed re-pinging unacknowledged alert",
                    exc_info=ex,
                    extra={"guild_id": gid, "channel_id": alert.channel_id, "job": f"reping:{alert.kind}"},
                )


async def _trigger_slot_if_new(
    ctx: AppContext,
    guild: discord.Guild,
    *,
    kind: str,
    slot_key: str,
    channel_id: int,
    headline: str,
    role_ping: str,
    now_ts: int,
    ack_view_factory: object,
) -> None:
    existing = await get_active_alert(ctx, guild.id, kind)
    if existing is not None and existing.slot_key == slot_key:
        return

    if existing is not None and existing.msg_id:
        old_ch = guild.get_channel(existing.channel_id)
        if isinstance(old_ch, discord.TextChannel):
            try:
                await old_ch.get_partial_message(existing.msg_id).delete()
            except discord.HTTPException:
                pass

    ch = guild.get_channel(channel_id)
    if not isinstance(ch, discord.TextChannel):
        return

    embed = discord.Embed(
        title=headline,
        description="Click **✅ Mark Done** or react with ✅ once done to stop the 5-minute pings!",
        color=GOLD if kind == "cowshed" else GREEN,
    )
    embed.set_footer(text=f"Triggered at {uk_str(now_ts)} • Pings every 5 mins until acknowledged")

    view = ack_view_factory()  # type: ignore[operator]
    msg = await ch.send(content=role_ping, embed=embed, view=view, allowed_mentions=PING)
    try:
        await msg.add_reaction("✅")
    except discord.HTTPException:
        pass

    await ctx.db.run(
        "INSERT INTO active_alerts VALUES(?,?,?,?,?,?,0) "
        "ON CONFLICT(guild_id,kind) DO UPDATE SET slot_key=excluded.slot_key, "
        "channel_id=excluded.channel_id, msg_id=excluded.msg_id, last_ping=excluded.last_ping, ack=0",
        (guild.id, kind, slot_key, channel_id, msg.id, now_ts),
    )
    await refresh_schedule_panel(ctx, guild, kind)


async def _reping_alert(
    ctx: AppContext,
    guild: discord.Guild,
    *,
    alert: ActiveAlert,
    role_ping: str,
    now_ts: int,
    ack_view_factory: object,
) -> None:
    ch = guild.get_channel(alert.channel_id)
    if not isinstance(ch, discord.TextChannel):
        await ctx.db.run(
            "UPDATE active_alerts SET last_ping=? WHERE guild_id=? AND kind=?",
            (now_ts, guild.id, alert.kind),
        )
        return

    try:
        await ch.get_partial_message(alert.msg_id).delete()
    except discord.HTTPException:
        pass

    label = "🐄 **COW FEED & MILK REMINDER**" if alert.kind == "cowshed" else "🌱 **PLANTATION NOURISH REMINDER**"
    slot_label = slot_label_from_key(alert.slot_key)
    embed = discord.Embed(
        title=f"⏰ {label} (Pending)",
        description=(
            f"Slot `{slot_label} UK` is still waiting!\n"
            "Click **✅ Mark Done** or react with ✅ to stop the pings."
        ),
        color=RED,
    )
    embed.set_footer(text=f"Re-pinged at {uk_str(now_ts)}")

    try:
        view = ack_view_factory()  # type: ignore[operator]
        new_msg = await ch.send(content=role_ping, embed=embed, view=view, allowed_mentions=PING)
        try:
            await new_msg.add_reaction("✅")
        except discord.HTTPException:
            pass
        new_msg_id = new_msg.id
    except (discord.Forbidden, discord.NotFound):
        logger.warning(
            "Cannot send schedule re-ping; pausing until next attempt",
            extra={"guild_id": guild.id, "channel_id": ch.id, "job": f"reping:{alert.kind}"},
        )
        new_msg_id = alert.msg_id

    await ctx.db.run(
        "UPDATE active_alerts SET msg_id=?, last_ping=? WHERE guild_id=? AND kind=?",
        (new_msg_id, now_ts, guild.id, alert.kind),
    )


def format_schedule_times(now_ts: int) -> tuple[int, str, int, str]:
    """Return next cowshed and plantation timestamps and labels."""
    cow_ts, cow_label = next_cow_slot(now_ts)
    plant_ts, plant_label = next_plant_slot(now_ts)
    return cow_ts, cow_label, plant_ts, plant_label
