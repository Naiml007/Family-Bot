"""Discord Bot factory, module auto-loader, and global interaction error handler."""

from __future__ import annotations

import math
import time
import traceback
from pathlib import Path

import discord
import structlog
from discord import app_commands
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from familybot.core.config import Settings
from familybot.core.embeds import error_embed, warning_embed
from familybot.core.errors import AppError
from familybot.core.interactions import SAFE_ALLOWED_MENTIONS
from familybot.core.logging import get_correlation_id, new_correlation_id
from familybot.db.base import ping_db
from familybot.db.uow import SqlUnitOfWorkFactory
from familybot.modules.admin.schemas import RuntimeSnapshot
from familybot.observability.health import HealthSnapshot

log = structlog.get_logger()


def discover_module_extensions(modules_dir: Path | None = None) -> list[str]:
    """Return sorted extension import paths for all `modules/*/cog.py` files."""
    if modules_dir is None:
        modules_dir = Path(__file__).resolve().parent / "modules"

    extensions: list[str] = []
    if not modules_dir.is_dir():
        return extensions

    for child in sorted(modules_dir.iterdir(), key=lambda p: p.name):
        if child.is_dir() and not child.name.startswith("_") and (child / "cog.py").is_file():
            extensions.append(f"familybot.modules.{child.name}.cog")
    return extensions


class FamilyCommandTree(app_commands.CommandTree):
    """CommandTree that binds a fresh correlation ID to every interaction."""

    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        new_correlation_id()
        return await super().interaction_check(interaction)


class FamilyBot(commands.Bot):
    """Main Discord bot instance holding DB/UoW wiring and runtime probes."""

    def __init__(
        self,
        *,
        settings: Settings,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        intents = discord.Intents.default()
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            allowed_mentions=SAFE_ALLOWED_MENTIONS,
            tree_cls=FamilyCommandTree,
        )
        self.settings = settings
        self.engine = engine
        self.session_factory = session_factory
        self.uow_factory = SqlUnitOfWorkFactory(session_factory)
        self.started_at_monotonic = time.monotonic()

    async def setup_hook(self) -> None:
        """Auto-load feature cogs, optional dev tools, error handler, and command sync."""
        self.tree.on_error = self._on_app_command_error

        for ext in discover_module_extensions():
            await self.load_extension(ext)
            log.info("extension.loaded", extension=ext)

        if self.settings.ENV == "dev":
            try:
                await self.load_extension("jishaku")
                log.info("extension.loaded", extension="jishaku")
            except commands.ExtensionError as exc:
                log.warning("extension.jishaku_skipped", reason=str(exc))

        if self.settings.DISCORD_GUILD_ID is not None:
            guild = discord.Object(id=self.settings.DISCORD_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("commands.synced", scope=f"guild:{self.settings.DISCORD_GUILD_ID}")
        else:
            await self.tree.sync()
            log.info("commands.synced", scope="global")

    async def on_ready(self) -> None:
        user = self.user
        log.info(
            "bot.ready",
            bot_user=str(user) if user else "unknown",
            bot_id=user.id if user else None,
            guild_count=len(self.guilds),
        )

    def get_runtime_snapshot(self) -> RuntimeSnapshot:
        """Return runtime status without leaking discord.py objects to services."""
        raw_latency = self.latency
        ws_latency_ms = raw_latency * 1000.0 if math.isfinite(raw_latency) else None
        loaded_modules = tuple(
            ext.removeprefix("familybot.modules.").removesuffix(".cog")
            for ext in sorted(self.extensions)
            if ext.startswith("familybot.modules.")
        )
        return RuntimeSnapshot(
            uptime_seconds=time.monotonic() - self.started_at_monotonic,
            ws_latency_ms=ws_latency_ms,
            loaded_modules=loaded_modules,
            version=self.settings.VERSION,
            git_sha=self.settings.GIT_SHA,
        )

    async def ping_database(self) -> float | None:
        """Ping PostgreSQL and return latency in milliseconds, or None on error."""
        return await ping_db(self.session_factory)

    async def health_probe(self) -> HealthSnapshot:
        """Build a HealthSnapshot for the /healthz HTTP endpoint."""
        db_latency = await self.ping_database()
        db_ok = db_latency is not None
        return HealthSnapshot(
            ok=db_ok,
            db_ok=db_ok,
            db_latency_ms=db_latency,
            uptime_seconds=time.monotonic() - self.started_at_monotonic,
            version=self.settings.VERSION,
        )

    async def _send_interaction_error(
        self, interaction: discord.Interaction, embed: discord.Embed
    ) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(
                embed=embed, ephemeral=True, allowed_mentions=SAFE_ALLOWED_MENTIONS
            )
        else:
            await interaction.response.send_message(
                embed=embed, ephemeral=True, allowed_mentions=SAFE_ALLOWED_MENTIONS
            )

    async def _post_error_channel(
        self,
        interaction: discord.Interaction,
        cid: str,
        exc: BaseException,
    ) -> None:
        if interaction.guild is None:
            return
        try:
            async with self.uow_factory.open() as uow:
                cfg = await uow.guild_settings.get(interaction.guild.id)
            if cfg is None or cfg.error_channel_id is None:
                return
            channel = interaction.guild.get_channel(cfg.error_channel_id)
            if not isinstance(channel, discord.TextChannel):
                return
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            truncated = tb[-1800:]
            cmd_name = interaction.command.qualified_name if interaction.command else "unknown"
            embed = error_embed(
                f"Unhandled Error (`{cid}`)",
                f"Command: `/{cmd_name}` • User: <@{interaction.user.id}>\n```py\n{truncated}\n```",
            )
            await channel.send(embed=embed, allowed_mentions=SAFE_ALLOWED_MENTIONS)
        except Exception:
            log.exception("error_channel.post_failed", correlation_id=cid)

    async def _on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        cid = get_correlation_id() or new_correlation_id()
        cause: BaseException = (
            error.original if isinstance(error, app_commands.CommandInvokeError) else error
        )

        if isinstance(cause, AppError):
            log.warning(
                "command.app_error",
                code=cause.code,
                user_message=cause.user_message,
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
            )
            embed = warning_embed(
                "Could Not Complete Action",
                f"{cause.user_message}\n\nError ref: `{cid}`",
            )
            await self._send_interaction_error(interaction, embed)
            return

        if isinstance(cause, app_commands.CheckFailure):
            log.warning(
                "command.check_failure",
                reason=str(cause),
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
            )
            embed = warning_embed(
                "Action Not Allowed",
                f"You cannot run this command here.\n\nError ref: `{cid}`",
            )
            await self._send_interaction_error(interaction, embed)
            return

        log.error(
            "command.unhandled_error",
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            exc_info=(type(cause), cause, cause.__traceback__),
        )
        embed = error_embed(
            "Unexpected Error",
            f"Something went wrong while running this command.\n\nError ref: `{cid}`",
        )
        await self._send_interaction_error(interaction, embed)
        await self._post_error_channel(interaction, cid, cause)
