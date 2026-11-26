import discord
from discord import app_commands

from thesnow.core.context import AppContext
from thesnow.core.panels import PanelSpec

from .embeds import build_seeds_panel_embed
from .service import get_seed_stock
from .views import SeedsView


def setup(bot: discord.Client, tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register the Seeds panel with the application context."""

    async def build_embed(guild: discord.Guild) -> discord.Embed:
        stock = await get_seed_stock(ctx.db, guild.id)
        return build_seeds_panel_embed(stock, guild)

    ctx.panels.register(
        PanelSpec(
            key="seeds",
            label="Seeds (Plantation/Cow Shed)",
            build_embed=build_embed,
            build_view=lambda: SeedsView(ctx),
        )
    )
