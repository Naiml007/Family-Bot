"""Slash commands for /cowshed."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from familybot.core.embeds import info_embed, success_embed
from familybot.core.interactions import SAFE_ALLOWED_MENTIONS, build_actor_context
from familybot.modules.cowshed.embeds import sync_collect_message
from familybot.modules.cowshed.service import CowshedService
from familybot.modules.cowshed.views import CollectCowsView


class CowshedCog(commands.Cog, name="cowshed"):
    """Cow Shed module commands."""

    def __init__(self, bot: commands.Bot, service: CowshedService) -> None:
        self.bot = bot
        self.service = service

    @app_commands.command(name="cowshed", description="Feed the cows / check collection time")
    async def cowshed(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        actor = build_actor_context(interaction)
        state = await self.service.status(actor)
        next_due = state.collect_at
        description = f"Collect due at: `{next_due}`" if next_due else "Collect time not set yet."
        embed = info_embed("Cow Shed Status", description)
        await interaction.followup.send(
            embed=embed,
            allowed_mentions=SAFE_ALLOWED_MENTIONS,
            view=CollectCowsView(self.service),
        )

    @app_commands.command(
        name="feed", description="Feed the cows and start the collection countdown"
    )
    async def feed(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        actor = build_actor_context(interaction)
        state = await self.service.feed(actor)
        embed = success_embed(
            "Cows Fed",
            f"Milk collection is due at: `{state.collect_at}`",
        )
        await interaction.followup.send(embed=embed, allowed_mentions=SAFE_ALLOWED_MENTIONS)

        channel_id = state.reminders_channel_id
        channel = self.bot.get_channel(channel_id) if channel_id is not None else None
        if isinstance(channel, discord.TextChannel):
            await sync_collect_message(
                channel,
                state.reminder_message_id,
                service=self.service,
                guild_id=actor.guild_id,
                collect_at=state.collect_at,
                last_reminder_at=state.last_reminder_at,
            )

    @app_commands.command(
        name="stop_reminders", description="Stop repeating collect-time reminders"
    )
    async def stop_reminders(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        actor = build_actor_context(interaction)
        await self.service.stop_reminders(actor)
        await interaction.followup.send(
            embed=success_embed("Reminders Stopped", "Milk collect reminders stopped."),
            allowed_mentions=SAFE_ALLOWED_MENTIONS,
        )

    @app_commands.command(
        name="set_channel", description="Set the channel for the Milk Collect embed"
    )
    async def set_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        actor = build_actor_context(interaction)
        await self.service.set_reminders_channel(actor, channel_id=channel.id)
        await interaction.followup.send(
            embed=success_embed(
                "Reminders Channel Set", f"Milk Collect updates go to {channel.mention}."
            ),
            allowed_mentions=SAFE_ALLOWED_MENTIONS,
        )

    @app_commands.command(name="set_role", description="Set the role pinged when collection is due")
    async def set_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        await interaction.response.defer(ephemeral=True)
        actor = build_actor_context(interaction)
        await self.service.set_collect_role(actor, role_id=role.id)
        await interaction.followup.send(
            embed=success_embed("Collect Role Set", f"Collection pings now use `{role.name}`."),
            allowed_mentions=SAFE_ALLOWED_MENTIONS,
        )


async def setup(bot: commands.Bot) -> None:
    """Register the cowshed cog."""
    service = CowshedService(bot.uow_factory)  # type: ignore[arg-type]
    await bot.add_cog(CowshedCog(bot, service))
    bot.add_view(CollectCowsView(service))
