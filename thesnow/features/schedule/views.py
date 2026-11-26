from typing import Any

import discord
from discord import app_commands

from thesnow.core.context import AppContext
from thesnow.core.errors import BaseView, safe_reply

from .service import acknowledge_alert, get_unacked_alert_by_message, refresh_schedule_panel


class AlertAckView(BaseView):
    """Persistent button view attached to Cow Shed and Plantation alert pings."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="Mark Done", emoji="✅", style=discord.ButtonStyle.success, custom_id="alert:ack")
    async def mark_done(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "schedule:ack"):
            return
        if interaction.guild is None or interaction.message is None:
            return
        alert = await get_unacked_alert_by_message(self.ctx, interaction.guild.id, interaction.message.id)
        if alert is None:
            await safe_reply(interaction, "✅ This alert was already acknowledged.")
            return
        await interaction.response.defer(ephemeral=True)
        acked = await acknowledge_alert(self.ctx, interaction.guild, interaction.user.id, alert)
        if acked:
            await safe_reply(interaction, f"✅ Acknowledged **{alert.kind}** alert.")
        else:
            await safe_reply(interaction, "✅ This alert was already acknowledged.")


async def handle_schedule_reaction(
    ctx: AppContext,
    bot: discord.Client,
    payload: discord.RawReactionActionEvent,
) -> None:
    """Process ✅ reactions on active alerts using DB-first lookup and fail-closed role verification."""
    if payload.guild_id is None or bot.user is None or payload.user_id == bot.user.id:
        return
    if str(payload.emoji) != "✅":
        return

    alert = await get_unacked_alert_by_message(ctx, payload.guild_id, payload.message_id)
    if alert is None:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    member = await ctx.permissions.authorize_reaction_member(guild, payload)
    if member is None:
        return

    await acknowledge_alert(ctx, guild, member.id, alert)


def register_schedule_commands(tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register Cow Shed and Plantation setup/stop slash commands."""

    @tree.command(
        name="plantation_setup",
        description="Configure fixed timers & UK-time Cow Shed / Plantation reminders",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(
        cowshed_channel="Channel for Cow Feed & Milk timer + reminders",
        plantation_channel="Channel for Plantation nourish timer + reminders",
        role="Role to ping every 5 minutes until acknowledged",
    )
    async def plantation_setup(
        interaction: discord.Interaction,
        cowshed_channel: discord.TextChannel,
        plantation_channel: discord.TextChannel,
        role: discord.Role,
    ) -> None:
        if not await ctx.permissions.authorize(interaction, "admin:plantation_setup"):
            return
        if interaction.guild is None:
            return
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        for kind, ch in (("cowshed", cowshed_channel), ("plantation", plantation_channel)):
            cfg = await ctx.config.get_many(guild.id, f"{kind}_panel_msg", f"{kind}_rem_ch")
            old_mid, old_cid = cfg[f"{kind}_panel_msg"], cfg[f"{kind}_rem_ch"]
            if old_mid and old_cid and old_mid.isdigit() and old_cid.isdigit():
                old_ch = guild.get_channel(int(old_cid))
                if isinstance(old_ch, discord.TextChannel):
                    try:
                        await old_ch.get_partial_message(int(old_mid)).delete()
                    except discord.HTTPException:
                        pass

        await ctx.config.set(guild.id, "cowshed_rem_ch", cowshed_channel.id)
        await ctx.config.set(guild.id, "plantation_rem_ch", plantation_channel.id)
        await ctx.config.set(guild.id, "plantation_rem_role", role.id)
        await ctx.config.set(guild.id, "plantation_rem_enabled", "1")

        cow_embed = await ctx.panels.get("cowshed").build_embed(guild)
        plant_embed = await ctx.panels.get("plantation").build_embed(guild)
        cow_msg = await cowshed_channel.send(embed=cow_embed)
        plant_msg = await plantation_channel.send(embed=plant_embed)
        await ctx.config.set(guild.id, "cowshed_panel_msg", cow_msg.id)
        await ctx.config.set(guild.id, "plantation_panel_msg", plant_msg.id)
        ctx.scheduler.notify()

        roles_cfg = await ctx.config.get_many(guild.id, "mod_role", "deputy_role")
        role_note = (
            "\n⚠️ *Reminder: run `/set_roles` so moderators/deputies can acknowledge alerts.*"
            if not roles_cfg["mod_role"] and not roles_cfg["deputy_role"]
            else ""
        )
        await safe_reply(
            interaction,
            "✅ **Fixed Timers & Reminders Configured (UK Time)**\n"
            f"🐄 **Cow Shed** → {cowshed_channel.mention} "
            "(`01:00, 04:00, 07:00, 10:00, 13:00, 16:00, 19:00, 22:00` UK)\n"
            f"🌱 **Plantation** → {plantation_channel.mention} (Every hour at `__:30` UK)\n"
            f"🔔 **Ping Role:** {role.mention} (pings every 5 mins until acknowledged){role_note}",
        )

    @tree.command(name="plantation_stop", description="Disable automated Cow Shed & Plantation reminders")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def plantation_stop(interaction: discord.Interaction) -> None:
        if not await ctx.permissions.authorize(interaction, "admin:plantation_stop"):
            return
        if interaction.guild is None:
            return
        await interaction.response.defer(ephemeral=True)
        await ctx.config.set(interaction.guild.id, "plantation_rem_enabled", "0")
        await ctx.db.run("DELETE FROM active_alerts WHERE guild_id=?", (interaction.guild.id,))
        await refresh_schedule_panel(ctx, interaction.guild, "cowshed")
        await refresh_schedule_panel(ctx, interaction.guild, "plantation")
        ctx.scheduler.notify()
        await safe_reply(interaction, "🛑 Cow Shed & Plantation reminders have been disabled.")
