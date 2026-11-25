"""Slash commands for /admin (thin Discord layer)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
import structlog
from discord import app_commands
from discord.ext import commands

from familybot.core.embeds import info_embed, success_embed
from familybot.core.errors import UserInputError
from familybot.core.interactions import SAFE_ALLOWED_MENTIONS, build_actor_context
from familybot.core.time import format_dt
from familybot.modules.admin.service import AdminService

if TYPE_CHECKING:
    from familybot.app import FamilyBot

log = structlog.get_logger()


def _format_uptime(seconds: float) -> str:
    total = int(seconds)
    days, rem = divmod(total, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or parts:
        parts.append(f"{hours}h")
    if minutes or parts:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


class AdminCog(commands.Cog):
    """Thin slash-command handlers for bot administration and diagnostics."""

    admin_group = app_commands.Group(
        name="admin",
        description="Bot administration, configuration, and diagnostics",
        guild_only=True,
    )
    module_group = app_commands.Group(
        name="module",
        description="Enable or disable feature modules for this server",
        parent=admin_group,
        guild_only=True,
    )

    def __init__(self, bot: FamilyBot, service: AdminService) -> None:
        self.bot = bot
        self.service = service

    async def _post_log_channel(
        self,
        guild: discord.Guild | None,
        log_channel_id: int | None,
        embed: discord.Embed,
    ) -> None:
        if guild is None or log_channel_id is None:
            return
        try:
            channel = guild.get_channel(log_channel_id) or await guild.fetch_channel(log_channel_id)
            if isinstance(channel, discord.TextChannel):
                await channel.send(embed=embed, allowed_mentions=SAFE_ALLOWED_MENTIONS)
        except (discord.NotFound, discord.Forbidden) as exc:
            log.warning("log_channel.post_failed", channel_id=log_channel_id, reason=str(exc))

    @admin_group.command(
        name="status",
        description="Show bot uptime, latency, DB health, and modules",
    )
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        actor = build_actor_context(interaction)
        dto = await self.service.get_status(actor)

        embed = info_embed("Bot Status")
        embed.add_field(name="Uptime", value=_format_uptime(dto.uptime_seconds), inline=True)
        embed.add_field(
            name="Discord Latency",
            value=f"{dto.ws_latency_ms:.0f} ms" if dto.ws_latency_ms is not None else "N/A",
            inline=True,
        )
        embed.add_field(
            name="DB Ping",
            value=f"{dto.db_latency_ms:.1f} ms" if dto.db_latency_ms is not None else "ERROR",
            inline=True,
        )
        reminders_value = (
            f"Pending: {dto.pending_reminders} | Failed: {dto.failed_reminders}"
            if dto.pending_reminders is not None and dto.failed_reminders is not None
            else "Scheduler not active (Phase 1)"
        )
        embed.add_field(name="Reminders", value=reminders_value, inline=True)
        version_str = f"{dto.version} ({dto.git_sha[:7]})" if dto.git_sha else dto.version
        embed.add_field(name="Version", value=version_str, inline=True)
        embed.add_field(
            name="Loaded Modules",
            value=", ".join(dto.loaded_modules) if dto.loaded_modules else "None",
            inline=False,
        )
        await interaction.followup.send(
            embed=embed, ephemeral=True, allowed_mentions=SAFE_ALLOWED_MENTIONS
        )

    @admin_group.command(name="config", description="View or update server settings")
    @app_commands.describe(
        timezone="IANA timezone (e.g. UTC, America/New_York, Europe/London)",
        log_channel="Channel for shared-state audit announcements",
        error_channel="Channel for unexpected error tracebacks",
        leader_role="Role mapped to Leader tier",
        admin_role="Role mapped to Admin tier",
        member_role="Role mapped to Member tier",
    )
    async def config(
        self,
        interaction: discord.Interaction,
        timezone: str | None = None,
        log_channel: discord.TextChannel | None = None,
        error_channel: discord.TextChannel | None = None,
        leader_role: discord.Role | None = None,
        admin_role: discord.Role | None = None,
        member_role: discord.Role | None = None,
    ) -> None:
        has_updates = any(
            v is not None
            for v in (timezone, log_channel, error_channel, leader_role, admin_role, member_role)
        )
        await interaction.response.defer(ephemeral=not has_updates)
        actor = build_actor_context(interaction)

        if has_updates:
            cfg = await self.service.update_config(
                actor,
                timezone=timezone,
                log_channel_id=log_channel.id if log_channel else None,
                error_channel_id=error_channel.id if error_channel else None,
                leader_role_id=leader_role.id if leader_role else None,
                admin_role_id=admin_role.id if admin_role else None,
                member_role_id=member_role.id if member_role else None,
            )
            embed = success_embed("Server Configuration Updated")
        else:
            cfg = await self.service.get_config(actor)
            embed = info_embed("Server Configuration")

        embed.add_field(name="Timezone", value=cfg.timezone, inline=True)
        embed.add_field(
            name="Log Channel",
            value=f"<#{cfg.log_channel_id}>" if cfg.log_channel_id else "Not set",
            inline=True,
        )
        embed.add_field(
            name="Error Channel",
            value=f"<#{cfg.error_channel_id}>" if cfg.error_channel_id else "Not set",
            inline=True,
        )
        roles_text = (
            "\n".join(
                f"**{k}**: "
                + (", ".join(f"<@&{rid}>" for rid in v) if isinstance(v, list) else f"<@&{v}>")
                for k, v in cfg.role_map.items()
            )
            or "Default (Server Admin = Leader)"
        )
        embed.add_field(name="Role Mapping", value=roles_text, inline=False)

        await interaction.followup.send(
            embed=embed, ephemeral=not has_updates, allowed_mentions=SAFE_ALLOWED_MENTIONS
        )
        if has_updates:
            await self._post_log_channel(interaction.guild, cfg.log_channel_id, embed)

    @module_group.command(name="enable", description="Enable a module for this server")
    async def module_enable(self, interaction: discord.Interaction, module: str) -> None:
        await interaction.response.defer()
        actor = build_actor_context(interaction)
        cfg = await self.service.set_module_enabled(actor, module_name=module, enabled=True)
        embed = success_embed(
            "Module Enabled",
            f"Module `{module.strip().lower()}` is now enabled.",
        )
        await interaction.followup.send(embed=embed, allowed_mentions=SAFE_ALLOWED_MENTIONS)
        await self._post_log_channel(interaction.guild, cfg.log_channel_id, embed)

    @module_group.command(name="disable", description="Disable a module for this server")
    async def module_disable(self, interaction: discord.Interaction, module: str) -> None:
        await interaction.response.defer()
        actor = build_actor_context(interaction)
        cfg = await self.service.set_module_enabled(actor, module_name=module, enabled=False)
        embed = success_embed(
            "Module Disabled", f"Module `{module.strip().lower()}` is now disabled."
        )
        await interaction.followup.send(embed=embed, allowed_mentions=SAFE_ALLOWED_MENTIONS)
        await self._post_log_channel(interaction.guild, cfg.log_channel_id, embed)

    @admin_group.command(name="reload", description="Reload a bot feature module")
    async def reload_module(self, interaction: discord.Interaction, module: str) -> None:
        await interaction.response.defer(ephemeral=True)
        actor = build_actor_context(interaction)
        await self.service.assert_admin(actor, action="reload modules")

        ext = f"familybot.modules.{module.strip().lower()}.cog"
        try:
            await self.bot.reload_extension(ext)
        except commands.ExtensionError as exc:
            raise UserInputError(f"Failed to reload `{ext}`: {exc}") from exc

        await self.service.record_runtime_action(
            actor,
            action="module.reloaded",
            entity_id=ext,
            payload={"extension": ext},
        )
        embed = success_embed("Module Reloaded", f"Reloaded `{ext}`.")
        await interaction.followup.send(
            embed=embed, ephemeral=True, allowed_mentions=SAFE_ALLOWED_MENTIONS
        )

    @admin_group.command(name="sync", description="Sync slash commands to this server or globally")
    async def sync(self, interaction: discord.Interaction, global_sync: bool = False) -> None:
        await interaction.response.defer(ephemeral=True)
        actor = build_actor_context(interaction)
        await self.service.assert_admin(actor, action="sync slash commands")

        if global_sync or interaction.guild is None:
            synced = await self.bot.tree.sync()
            scope = "global"
        else:
            self.bot.tree.copy_global_to(guild=interaction.guild)
            synced = await self.bot.tree.sync(guild=interaction.guild)
            scope = f"guild:{interaction.guild.id}"

        await self.service.record_runtime_action(
            actor,
            action="commands.synced",
            entity_id=scope,
            payload={"count": len(synced)},
        )
        embed = success_embed(
            "Slash Commands Synced", f"Synced {len(synced)} command(s) ({scope})."
        )
        await interaction.followup.send(
            embed=embed, ephemeral=True, allowed_mentions=SAFE_ALLOWED_MENTIONS
        )

    @admin_group.command(
        name="debug",
        description="Look up audit entries by correlation reference ID",
    )
    async def debug(self, interaction: discord.Interaction, ref: str) -> None:
        await interaction.response.defer(ephemeral=True)
        actor = build_actor_context(interaction)
        tz_name, entries = await self.service.debug_correlation_id(actor, correlation_id=ref)

        if not entries:
            embed = info_embed("Debug Lookup", f"No audit entries found for ref `{ref}`.")
        else:
            lines = [
                f"`{format_dt(e.created_at, tz_name)}` • **{e.action}** "
                f"on `{e.entity}:{e.entity_id}` by <@{e.actor_id}>"
                for e in entries[:10]
            ]
            embed = info_embed(f"Debug Ref: {ref}", "\n".join(lines))

        await interaction.followup.send(
            embed=embed, ephemeral=True, allowed_mentions=SAFE_ALLOWED_MENTIONS
        )

    @admin_group.command(name="logs", description="Show recent audit log entries")
    async def logs(self, interaction: discord.Interaction, limit: int = 10) -> None:
        await interaction.response.defer(ephemeral=True)
        actor = build_actor_context(interaction)
        tz_name, entries = await self.service.list_recent_logs(actor, limit=limit)

        if not entries:
            embed = info_embed("Audit Logs", "No audit entries recorded yet.")
        else:
            lines = [
                f"`{format_dt(e.created_at, tz_name)}` • **{e.action}** "
                f"(`{e.correlation_id}`) by <@{e.actor_id}>"
                for e in entries
            ]
            embed = info_embed("Recent Audit Logs", "\n".join(lines))

        await interaction.followup.send(
            embed=embed, ephemeral=True, allowed_mentions=SAFE_ALLOWED_MENTIONS
        )


async def setup(bot: FamilyBot) -> None:
    """Extension entrypoint auto-loaded by FamilyBot."""
    service = AdminService(uow_factory=bot.uow_factory, runtime_probe=bot)
    await bot.add_cog(AdminCog(bot=bot, service=service))
