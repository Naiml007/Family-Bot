"""Background poller for guild reminders."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
import structlog

from familybot.core.time import utcnow
from familybot.modules.cowshed.embeds import sync_collect_message
from familybot.modules.cowshed.service import CowshedService

if TYPE_CHECKING:
    from familybot.app import FamilyBot

log = structlog.get_logger()


async def run_cow_reminder_loop(bot: FamilyBot) -> None:
    """Edit one Milk Collect embed per guild every 5 minutes until stopped."""
    service = CowshedService(bot.uow_factory)
    while True:
        try:
            async with bot.uow_factory.open() as uow:
                rows = await uow.cow_shed_state.get_due_reminders()
                due = [
                    row
                    for row in rows
                    if row.last_reminder_at is None
                    or utcnow() - row.last_reminder_at >= timedelta(minutes=5)
                ]
                for row in due:
                    await uow.cow_shed_state.update(row.guild_id, last_reminder_at=utcnow())
                await uow.commit()

            for row in due:
                async with bot.uow_factory.open() as uow:
                    cfg = await uow.guild_settings.get(row.guild_id)
                if cfg is None or cfg.reminders_channel_id is None:
                    continue
                channel = bot.get_channel(cfg.reminders_channel_id)
                if not isinstance(channel, discord.TextChannel):
                    continue
                mention = f"<@&{row.collect_role_id}>" if row.collect_role_id else None
                await sync_collect_message(
                    channel,
                    row.reminder_message_id,
                    service=service,
                    guild_id=row.guild_id,
                    collect_at=row.collect_at,
                    last_reminder_at=utcnow(),
                    mention=mention,
                )
        except Exception:
            log.exception("cowshed_reminder_loop.error")
        await asyncio.sleep(30)
