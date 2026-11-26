import time

import discord
from discord import app_commands

from thesnow.core.context import AppContext
from thesnow.core.errors import safe_reply
from thesnow.shared.time import parse_uk_hhmm, uk_str

from .embeds import build_reminders_list_embed
from .service import (
    add_reminder,
    delete_reminder,
    list_reminders,
    reset_diplomacy,
    setup_diplomacy,
)


def register_reminder_commands(tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register /reminder and /diplomacy slash commands."""
    rem = app_commands.Group(name="reminder", description="Custom repeating reminders (UK time)", guild_only=True)

    @rem.command(name="add", description="Add a custom repeating reminder")
    @app_commands.describe(
        chapter="Chapter name",
        role="Role to ping",
        channel="Where to send it",
        every_hours="Repeat every X hours (3, 0.5, 24…)",
        message="Custom text (optional)",
        first_at="First ping at HH:MM UK time (optional)",
    )
    async def rem_add(
        interaction: discord.Interaction,
        chapter: str,
        role: discord.Role,
        channel: discord.TextChannel,
        every_hours: app_commands.Range[float, 0.1, 720.0],
        message: str | None = None,
        first_at: str | None = None,
    ) -> None:
        if not await ctx.permissions.authorize(interaction, "reminders:manage"):
            return
        if interaction.guild_id is None:
            return
        if first_at:
            try:
                nxt = parse_uk_hhmm(first_at)
            except ValueError:
                await safe_reply(interaction, "❌ `first_at` must look like `18:30` (24h UK time).")
                return
        else:
            nxt = int(time.time() + every_hours * 3600)

        interval_min = max(1, round(every_hours * 60))
        reminder_id = await add_reminder(
            ctx.db,
            interaction.guild_id,
            chapter=chapter.strip()[:100],
            channel_id=channel.id,
            role_id=role.id,
            message=(message or f"Time for **{chapter}**!")[:500],
            interval_min=interval_min,
            next_run=nxt,
        )
        ctx.scheduler.notify()
        await safe_reply(
            interaction,
            f"✅ Reminder `#{reminder_id}` for **{chapter}** → {role.mention} every {every_hours:g}h. "
            f"First ping: **{uk_str(nxt)}** UK.",
        )

    @rem.command(name="list", description="Show all custom reminders")
    async def rem_list(interaction: discord.Interaction) -> None:
        if not await ctx.permissions.authorize(interaction, "reminders:read"):
            return
        if interaction.guild_id is None:
            return
        rows = await list_reminders(ctx.db, interaction.guild_id)
        await safe_reply(interaction, embed=build_reminders_list_embed(rows))

    @rem.command(name="remove", description="Delete a custom reminder by ID")
    async def rem_remove(interaction: discord.Interaction, reminder_id: int) -> None:
        if not await ctx.permissions.authorize(interaction, "reminders:manage"):
            return
        if interaction.guild_id is None:
            return
        await delete_reminder(ctx.db, interaction.guild_id, reminder_id)
        ctx.scheduler.notify()
        await safe_reply(interaction, f"🗑️ Reminder #{reminder_id} removed.")

    tree.add_command(rem)

    @tree.command(name="diplomacy_setup", description="Start the 7-day diplomacy reminder")
    @app_commands.guild_only()
    async def dip_setup(
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: discord.Role,
    ) -> None:
        if not await ctx.permissions.authorize(interaction, "reminders:manage"):
            return
        if interaction.guild_id is None:
            return
        nxt = await setup_diplomacy(ctx.db, interaction.guild_id, channel_id=channel.id, role_id=role.id)
        ctx.scheduler.notify()
        await safe_reply(interaction, f"✅ Diplomacy reminder set. Next ping: **{uk_str(nxt)}** UK.")

    @tree.command(name="diplomacy_done", description="Diplomacy taken – restart the 7-day timer")
    @app_commands.guild_only()
    async def dip_done(interaction: discord.Interaction) -> None:
        if not await ctx.permissions.authorize(interaction, "reminders:manage"):
            return
        if interaction.guild_id is None:
            return
        nxt = await reset_diplomacy(ctx.db, interaction.guild_id)
        ctx.scheduler.notify()
        await safe_reply(interaction, f"✅ Timer reset. Next diplomacy reminder: **{uk_str(nxt)}** UK.")
