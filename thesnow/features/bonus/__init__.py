import discord
from discord import app_commands

from thesnow.core.context import AppContext
from thesnow.core.panels import PanelSpec

from .embeds import build_bonus_log_panel_embed, build_ticket_panel_embed
from .service import get_bonus_stats
from .views import BonusLogView, CloseView, TicketView


def setup(bot: discord.Client, tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register bonus ticket and bonus payout log panels and views."""

    async def build_ticket_embed(guild: discord.Guild) -> discord.Embed:
        return build_ticket_panel_embed(guild)

    async def build_bonus_log_embed(guild: discord.Guild) -> discord.Embed:
        stats = await get_bonus_stats(ctx.db, guild.id)
        return build_bonus_log_panel_embed(stats, guild)

    ctx.panels.register(
        PanelSpec(
            key="bonus_ticket",
            label="Bonus Request Tickets",
            build_embed=build_ticket_embed,
            build_view=lambda: TicketView(ctx),
        )
    )
    ctx.panels.register(
        PanelSpec(
            key="bonus_log",
            label="Bonus Logs",
            build_embed=build_bonus_log_embed,
            build_view=lambda: BonusLogView(ctx),
        )
    )
    bot.add_view(CloseView(ctx))
