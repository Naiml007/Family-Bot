"""Buttons for the Cow Shed module."""

from __future__ import annotations

import discord

from familybot.modules.cowshed.service import CowshedService


class CollectCowsView(discord.ui.View):
    """Button that checks whether milk collection is due."""

    def __init__(self, service: CowshedService, guild_id: int) -> None:
        super().__init__(timeout=None)
        self.service = service
        self.guild_id = guild_id

    @discord.ui.button(  # type: ignore[reportArgumentType]
        label="Collect Cows",
        style=discord.ButtonStyle.primary,
        custom_id="cowshed:collect",
    )
    async def collect_button(
        self,
        interaction: discord.Interaction[discord.Client],
        item: discord.Button,
    ) -> None:
        result = await self.service.collect(self.guild_id)
        if not result.due:
            await interaction.response.send_message(
                "Milk collection is not due yet.", ephemeral=True
            )
            return
        await interaction.response.send_message("🔔 Milk collection is due now!", ephemeral=False)
