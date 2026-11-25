"""Persistent 'Milk Collect' embed and its channel message updater."""

from __future__ import annotations

from datetime import datetime

import discord

from familybot.core.embeds import COLOR_INFO, COLOR_WARNING, make_embed
from familybot.core.time import utcnow
from familybot.modules.cowshed.service import CowshedService
from familybot.modules.cowshed.views import CollectCowsView

_FOOTER = "Stops: /cowshed stop_reminders"


def collect_embed(collect_at: datetime | None, last_reminder_at: datetime | None) -> discord.Embed:
    """Build the single embed shown in the reminders channel."""
    if collect_at is None:
        return make_embed(
            title="Milk Collect",
            description="No collection scheduled. Use `/cowshed feed` first.",
            color=COLOR_INFO,
            footer_extra=_FOOTER,
        )

    due = utcnow() >= collect_at
    lines = [f"Collect <t:{int(collect_at.timestamp())}:R>"]
    if last_reminder_at is not None:
        lines.append(f"Last reminder <t:{int(last_reminder_at.timestamp())}:R>")
    return make_embed(
        title="Milk Collect" + (" — due now" if due else ""),
        description="\n".join(lines),
        color=COLOR_WARNING if due else COLOR_INFO,
        footer_extra=_FOOTER,
    )


async def sync_collect_message(
    channel: discord.TextChannel,
    message_id: int | None,
    *,
    service: CowshedService,
    guild_id: int,
    collect_at: datetime | None,
    last_reminder_at: datetime | None,
    mention: str | None = None,
) -> int:
    """Edit the one stored message, or create it when missing, and return its id."""
    embed = collect_embed(collect_at, last_reminder_at)
    view = CollectCowsView(service)
    allowed_mentions = discord.AllowedMentions(roles=True, users=False, everyone=False)
    if message_id is not None:
        try:
            await channel.get_partial_message(message_id).edit(
                content=mention, embed=embed, view=view, allowed_mentions=allowed_mentions
            )
            return message_id
        except discord.NotFound:
            pass
    message = await channel.send(
        content=mention, embed=embed, view=view, allowed_mentions=allowed_mentions
    )
    await service.set_reminder_message(guild_id, message.id)
    return message.id
