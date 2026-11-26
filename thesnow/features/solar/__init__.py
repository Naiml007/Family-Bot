import discord
from discord import app_commands

from thesnow.core.context import AppContext
from thesnow.core.panels import PanelSpec

from .embeds import build_solar_panel_embed
from .service import get_solar_stats
from .views import SolarView


def setup(bot: discord.Client, tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register the Solar Plantation panel with the application context."""

    async def build_embed(guild: discord.Guild) -> discord.Embed:
        stats = await get_solar_stats(ctx.db, ctx.config, guild.id)
        return build_solar_panel_embed(stats, guild)

    ctx.panels.register(
        PanelSpec(
            key="solar",
            label="Solar Plantation",
            build_embed=build_embed,
            build_view=lambda: SolarView(ctx),
        )
    )
