import discord
from discord import app_commands

from thesnow.core.context import AppContext
from thesnow.core.panels import PanelSpec

from .embeds import build_armory_panel_embed
from .service import ensure_armory_seeded, get_armory_rows
from .views import ArmoryView


def setup(bot: discord.Client, tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register the Family Armory panel with non-destructive seeding on /setup."""

    async def build_embed(guild: discord.Guild) -> discord.Embed:
        rows = await get_armory_rows(ctx.db, guild.id)
        return build_armory_panel_embed(rows, guild)

    ctx.panels.register(
        PanelSpec(
            key="armory",
            label="Armory",
            build_embed=build_embed,
            build_view=lambda: ArmoryView(ctx),
            on_setup=lambda guild_id: ensure_armory_seeded(ctx.db, guild_id),
        )
    )
