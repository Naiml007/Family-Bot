import discord
from discord import app_commands

from thesnow.core.context import AppContext
from thesnow.core.panels import PanelSpec

from .embeds import build_schedule_panel_embed
from .service import get_active_alert, process_uk_schedules
from .views import AlertAckView, handle_schedule_reaction, register_schedule_commands


def setup(bot: discord.Client, tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register Cow Shed and Plantation panels, alert view, and commands."""

    async def _build_cowshed(guild: discord.Guild) -> discord.Embed:
        alert = await get_active_alert(ctx, guild.id, "cowshed")
        last_done = await ctx.config.get(guild.id, "cowshed_last_done")
        return build_schedule_panel_embed("cowshed", alert=alert, last_done=last_done, guild=guild)

    async def _build_plantation(guild: discord.Guild) -> discord.Embed:
        alert = await get_active_alert(ctx, guild.id, "plantation")
        last_done = await ctx.config.get(guild.id, "plantation_last_done")
        return build_schedule_panel_embed("plantation", alert=alert, last_done=last_done, guild=guild)

    ctx.panels.register(PanelSpec(key="cowshed", label="Cow Shed Timer", build_embed=_build_cowshed))
    ctx.panels.register(PanelSpec(key="plantation", label="Plantation Timer", build_embed=_build_plantation))
    bot.add_view(AlertAckView(ctx))
    register_schedule_commands(tree, ctx)

    ctx.reaction_handlers.append(lambda payload: handle_schedule_reaction(ctx, bot, payload))
    ctx.tick_handlers.append(
        lambda now_ts: process_uk_schedules(
            ctx,
            bot,
            now_ts,
            ack_view_factory=lambda: AlertAckView(ctx),
        )
    )
