"""Slash commands for /cowshed."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from familybot.core.embeds import info_embed, success_embed
from familybot.core.interactions import SAFE_ALLOWED_MENTIONS, build_actor_context
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
            view=CollectCowsView(self.service, interaction.guild_id or 0),
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


async def setup(bot: commands.Bot) -> None:
    """Register the cowshed cog."""
    service = CowshedService(bot.uow_factory)  # type: ignore[arg-type]
    await bot.add_cog(CowshedCog(bot, service))
