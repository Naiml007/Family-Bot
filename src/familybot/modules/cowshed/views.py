"""Buttons for the Cow Shed module."""

from __future__ import annotations

import discord

from familybot.modules.cowshed.service import CowshedService


class CollectCowsView(discord.ui.View):
    """Button that checks whether milk collection is due."""

    def __init__(self, service: CowshedService) -> None:
        super().__init__(timeout=None)
        self.service = service

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
        result = await self.service.collect(interaction.guild_id or 0)
        if not result.due:
            await interaction.response.send_message(
                "Milk collection is not due yet.", ephemeral=True
            )
            return
        mention = f"<@&{result.collect_role_id}> " if result.collect_role_id else ""
        await interaction.response.send_message(
            f"{mention}🔔 Milk collection is due now!",
            allowed_mentions=discord.AllowedMentions(roles=True, users=False),
        )
