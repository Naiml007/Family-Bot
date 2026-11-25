"""Background poller for guild reminders."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
import structlog

from familybot.core.time import utcnow

if TYPE_CHECKING:
    from familybot.app import FamilyBot

log = structlog.get_logger()


async def run_cow_reminder_loop(bot: FamilyBot) -> None:
    """Poll due Cow Shed reminders and send to the guild log channel."""
    while True:
        try:
            async with bot.uow_factory.open() as uow:
                rows = await uow.cow_shed_state.get_due_reminders()
                for row in rows:
                    if row.last_reminder_at and utcnow() - row.last_reminder_at < timedelta(
                        minutes=5
                    ):
                        continue
                    await uow.cow_shed_state.update(
                        row.guild_id, last_reminder_at=utcnow(), reminders_active=True
                    )
                await uow.commit()

            for row in rows:
                guild = bot.get_guild(row.guild_id)
                if guild is None:
                    continue
                async with bot.uow_factory.open() as uow:
                    cfg = await uow.guild_settings.get(guild.id)
                if cfg is None or cfg.log_channel_id is None:
                    continue
                channel = guild.get_channel(cfg.log_channel_id)
                if isinstance(channel, discord.TextChannel):
                    await channel.send(
                        "Milk collection due. Use `/cowshed stop_reminders` to stop."
                    )
        except Exception:
            log.exception("cowshed_reminder_loop.error")
        await asyncio.sleep(30)
