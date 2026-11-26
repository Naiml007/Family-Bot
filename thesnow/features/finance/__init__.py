import discord
from discord import app_commands

from thesnow.core.context import AppContext
from thesnow.core.panels import PanelSpec

from .embeds import build_finance_panel_embed
from .service import get_active_loans
from .views import FinanceView


def setup(bot: discord.Client, tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register the Finance & Loans panel with the application context."""

    async def build_embed(guild: discord.Guild) -> discord.Embed:
        loans = await get_active_loans(ctx.db, guild.id)
        return build_finance_panel_embed(loans, guild)

    ctx.panels.register(
        PanelSpec(
            key="finance",
            label="Finance / Loans",
            build_embed=build_embed,
            build_view=lambda: FinanceView(ctx),
        )
    )
