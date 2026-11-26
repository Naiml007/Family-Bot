import discord
from discord import app_commands

from thesnow.core.context import AppContext
from thesnow.core.panels import PanelSpec

from .embeds import build_balance_panel_embed
from .service import get_balance_stats
from .views import BalanceView


def setup(bot: discord.Client, tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register the Family Balance panel with the application context."""

    async def build_embed(guild: discord.Guild) -> discord.Embed:
        stats = await get_balance_stats(ctx.db, guild.id, recent_limit=5)
        return build_balance_panel_embed(stats, guild)

    ctx.panels.register(
        PanelSpec(
            key="balance",
            label="Family Balance",
            build_embed=build_embed,
            build_view=lambda: BalanceView(ctx),
        )
    )
