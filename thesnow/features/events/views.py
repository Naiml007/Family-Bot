import time

import discord
from discord import app_commands

from thesnow.core.context import AppContext
from thesnow.core.errors import safe_reply
from thesnow.shared.constants import BLUE
from thesnow.shared.time import parse_uk_event_datetime, uk_str

from .embeds import build_events_list_embed
from .service import create_event, delete_event, list_upcoming_events


def register_event_commands(tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register event management slash commands."""

    @tree.command(name="event_create", description="Create an event + automatic reminders (UK time)")
    @app_commands.guild_only()
    @app_commands.describe(
        date="DD/MM/YYYY",
        time_uk="HH:MM (24h, UK time)",
        role="Role/family to tag",
        channel="Where to announce",
        remind_before_min="Minutes before to remind (0-10080)",
    )
    async def event_create(
        interaction: discord.Interaction,
        title: str,
        date: str,
        time_uk: str,
        role: discord.Role,
        channel: discord.TextChannel,
        remind_before_min: app_commands.Range[int, 0, 10080] = 30,
        description: str = "",
    ) -> None:
        if not await ctx.permissions.authorize(interaction, "events:manage"):
            return
        if interaction.guild_id is None:
            return
        try:
            start_ts = parse_uk_event_datetime(date, time_uk)
        except ValueError:
            await safe_reply(interaction, "❌ Use date like `25/12/2026` and valid UK time like `20:30`.")
            return

        if start_ts <= time.time():
            await safe_reply(interaction, "❌ That time is in the past (UK time).")
            return

        await interaction.response.defer(ephemeral=True)
        event_id = await create_event(
            ctx.db,
            interaction.guild_id,
            title=title.strip()[:100],
            description=description.strip()[:500],
            channel_id=channel.id,
            role_id=role.id,
            start_ts=start_ts,
            remind_min=int(remind_before_min),
        )
        ctx.scheduler.notify()

        embed = discord.Embed(title=f"📅 {title}", description=description or None, color=BLUE)
        embed.add_field(name="When (UK)", value=uk_str(start_ts))
        embed.add_field(name="Reminder", value=f"{remind_before_min} min before")
        try:
            await channel.send(
                role.mention,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
            announce_note = ""
        except discord.HTTPException:
            announce_note = " (Note: could not post initial announcement in target channel.)"

        await safe_reply(interaction, f"✅ Event `#{event_id}` created.{announce_note}")

    @tree.command(name="event_list", description="Upcoming events")
    @app_commands.guild_only()
    async def event_list(interaction: discord.Interaction) -> None:
        if not await ctx.permissions.authorize(interaction, "events:read"):
            return
        if interaction.guild_id is None:
            return
        rows = await list_upcoming_events(ctx.db, interaction.guild_id)
        await safe_reply(interaction, embed=build_events_list_embed(rows))

    @tree.command(name="event_delete", description="Delete an event by ID")
    @app_commands.guild_only()
    async def event_delete(interaction: discord.Interaction, event_id: int) -> None:
        if not await ctx.permissions.authorize(interaction, "events:manage"):
            return
        if interaction.guild_id is None:
            return
        await delete_event(ctx.db, interaction.guild_id, event_id)
        ctx.scheduler.notify()
        await safe_reply(interaction, f"🗑️ Event #{event_id} deleted.")
