import discord
from discord import app_commands

from thesnow.core.context import AppContext
from thesnow.core.panels import PanelSpec

from .embeds import build_storage_panel_embed
from .service import get_active_storage
from .views import StorageView


def setup(bot: discord.Client, tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register the Shared Storage panel with the application context."""

    async def build_embed(guild: discord.Guild) -> discord.Embed:
        items = await get_active_storage(ctx.db, guild.id)
        return build_storage_panel_embed(items, guild)

    ctx.panels.register(
        PanelSpec(
            key="storage",
            label="Shared Storage",
            build_embed=build_embed,
            build_view=lambda: StorageView(ctx),
        )
    )
