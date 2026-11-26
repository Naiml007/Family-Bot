import discord
from discord import app_commands

from thesnow.core.context import AppContext

from .service import process_due_events
from .views import register_event_commands


def setup(bot: discord.Client, tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register event slash commands and scheduler handler."""
    register_event_commands(tree, ctx)
    ctx.tick_handlers.append(lambda now_ts: process_due_events(ctx, bot, now_ts))
