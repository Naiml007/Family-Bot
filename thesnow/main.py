import logging

import discord
from discord import app_commands
from dotenv import load_dotenv

from thesnow.config import ConfigError, Settings, load_settings
from thesnow.core.context import AppContext
from thesnow.core.database import ConfigCache, Database
from thesnow.core.errors import handle_app_command_error, safe_reply
from thesnow.core.logging import configure_logging
from thesnow.core.migrations import migrate
from thesnow.core.panels import PanelRegistry
from thesnow.core.permissions import PermissionService
from thesnow.core.scheduler import DeadlineScheduler, next_deadline
from thesnow.features import armory, balance, bonus, events, finance, reminders, schedule, seeds, solar, storage

logger = logging.getLogger("thesnow")


async def compute_next_deadline(ctx: AppContext, now_ts: int) -> float | None:
    """Compute the earliest scheduled wakeup deadline across all guilds."""
    rem_rows = await ctx.db.many("SELECT next_run FROM reminders")
    reminder_times = [int(row["next_run"]) for row in rem_rows]

    event_rows = await ctx.db.many("SELECT start_ts, remind_min, remind_sent FROM events WHERE start_sent=0")
    event_times = [
        int(row["start_ts"]) - max(0, int(row["remind_min"])) * 60
        if not row["remind_sent"]
        else int(row["start_ts"])
        for row in event_rows
    ]

    alert_rows = await ctx.db.many("SELECT last_ping FROM active_alerts WHERE ack=0")
    alert_times = [int(row["last_ping"]) + 300 for row in alert_rows]

    fixed_row = await ctx.db.one(
        "SELECT 1 FROM config WHERE key='plantation_rem_enabled' AND value='1' LIMIT 1"
    )
    return next_deadline(
        now_ts,
        reminder_times,
        event_times,
        alert_times,
        fixed_schedules_enabled=fixed_row is not None,
    )


def register_admin_commands(tree: app_commands.CommandTree, ctx: AppContext) -> None:
    """Register core administrative /setup and /set_roles commands."""
    setup_choices = ctx.panels.choices()

    @tree.command(name="setup", description="Post a control panel in a channel (admin)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(feature=setup_choices)
    @app_commands.describe(
        feature="Which panel",
        panel_channel="Channel for the fixed panel",
        log_channel="Channel for logs",
    )
    async def setup_cmd(
        interaction: discord.Interaction,
        feature: app_commands.Choice[str],
        panel_channel: discord.TextChannel,
        log_channel: discord.TextChannel | None = None,
    ) -> None:
        if not await ctx.permissions.authorize(interaction, "admin:setup"):
            return
        if interaction.guild is None:
            return
        await interaction.response.defer(ephemeral=True)
        await ctx.panels.setup_panel(interaction.guild, feature.value, panel_channel, log_channel)
        roles_cfg = await ctx.config.get_many(interaction.guild.id, "mod_role", "deputy_role")
        role_note = (
            "\n⚠️ *Moderator/Deputy roles are not configured yet — run `/set_roles` to allow staff access.*"
            if not roles_cfg["mod_role"] and not roles_cfg["deputy_role"]
            else ""
        )
        await safe_reply(
            interaction,
            f"✅ {feature.name} panel posted in {panel_channel.mention}.{role_note}",
        )

    @tree.command(name="set_roles", description="Set moderator and deputy roles (admin)")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def set_roles(
        interaction: discord.Interaction,
        moderator: discord.Role,
        deputy: discord.Role,
    ) -> None:
        if not await ctx.permissions.authorize(interaction, "admin:set_roles"):
            return
        if interaction.guild_id is None:
            return
        await ctx.config.set(interaction.guild_id, "mod_role", moderator.id)
        await ctx.config.set(interaction.guild_id, "deputy_role", deputy.id)
        await safe_reply(interaction, f"✅ Moderator = {moderator.mention}, Deputy = {deputy.mention}")


class FamilyBot(discord.Client):
    """Composition root client wiring database, permissions, features, and scheduler."""

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.settings = settings
        self.tree = app_commands.CommandTree(self)
        self.tree.error(handle_app_command_error)
        self.schema_version = 0

        db = Database(settings.db_path)
        config = ConfigCache(db)
        permissions = PermissionService(config, settings.allowed_guild_ids)
        panels = PanelRegistry(config)

        async def _tick(now_ts: int) -> float | None:
            await self.wait_until_ready()
            for handler in self.ctx.tick_handlers:
                await handler(now_ts)
            return await compute_next_deadline(self.ctx, now_ts)

        scheduler = DeadlineScheduler(_tick)
        self.ctx = AppContext(
            settings=settings,
            db=db,
            config=config,
            permissions=permissions,
            panels=panels,
            scheduler=scheduler,
        )

    async def setup_hook(self) -> None:
        await self.ctx.db.connect()
        self.schema_version = await migrate(self.ctx.db)

        for module in (balance, seeds, solar, armory, storage, finance, bonus, schedule, reminders, events):
            module.setup(self, self.tree, self.ctx)

        for view in self.ctx.panels.persistent_views():
            self.add_view(view)

        register_admin_commands(self.tree, self.ctx)

        self.ctx.scheduler.start()

        gid = self.settings.guild_id
        if gid is not None:
            if self.settings.allowed_guild_ids and gid not in self.settings.allowed_guild_ids:
                logger.warning(
                    "GUILD_ID is not included in ALLOWED_GUILD_IDS; slash commands synced to a disallowed guild",
                    extra={"guild_id": gid},
                )
            guild_obj = discord.Object(gid)
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
        else:
            await self.tree.sync()

    async def close(self) -> None:
        await self.ctx.scheduler.stop()
        await self.ctx.db.close()
        await super().close()

    async def on_ready(self) -> None:
        logger.info(
            "Logged in as %s (schema_version=%s, guilds=%s)",
            self.user,
            self.schema_version,
            len(self.guilds),
        )
        for guild in list(self.guilds):
            if not self.ctx.permissions.is_guild_allowed(guild.id):
                logger.warning("Leaving guild not in allowlist", extra={"guild_id": guild.id})
                await guild.leave()
            else:
                await self.ctx.config.preload_guild(guild.id)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        if not self.ctx.permissions.is_guild_allowed(guild.id):
            logger.warning("Leaving newly joined guild not in allowlist", extra={"guild_id": guild.id})
            await guild.leave()
            return
        await self.ctx.config.preload_guild(guild.id)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        self.ctx.config.clear_guild(guild.id)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        for handler in self.ctx.reaction_handlers:
            await handler(payload)


def build_bot(settings: Settings) -> FamilyBot:
    """Create a configured FamilyBot instance without import-time side effects."""
    return FamilyBot(settings)


def run() -> None:
    """CLI and bot.py entry point."""
    load_dotenv()
    try:
        settings = load_settings()
    except ConfigError as ex:
        configure_logging().error("%s", ex)
        raise SystemExit(str(ex)) from ex

    configure_logging(settings.log_level)
    bot = build_bot(settings)
    bot.run(settings.discord_token, log_handler=None)


if __name__ == "__main__":
    run()
