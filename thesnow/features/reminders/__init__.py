import discord
from discord import app_commands

from thesnow.core.context import AppContext

from .service import process_due_reminders
from .views import register_reminder_commands


def setup(bot: discord.Client, tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register repeating reminders, diplomacy commands, and scheduler handler."""
    register_reminder_commands(tree, ctx)
    ctx.tick_handlers.append(lambda now_ts: process_due_reminders(ctx, bot, now_ts))
