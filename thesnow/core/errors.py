import asyncio
import logging
import random
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import discord
from discord import app_commands

from thesnow.shared.validation import Oops

logger = logging.getLogger("thesnow.errors")
T = TypeVar("T")


def new_error_id() -> str:
    """Generate a short correlation ID for log and user error matching."""
    return uuid.uuid4().hex[:8]


async def safe_reply(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    ephemeral: bool = True,
) -> None:
    """Send an interaction response or followup safely, suppressing Discord HTTP failures."""
    kwargs: dict[str, Any] = {"ephemeral": ephemeral}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed

    try:
        if interaction.response.is_done():
            await interaction.followup.send(**kwargs)
        else:
            await interaction.response.send_message(**kwargs)
    except discord.HTTPException:
        logger.warning(
            "Failed to send interaction reply",
            extra={
                "guild_id": interaction.guild_id,
                "user_id": getattr(interaction.user, "id", None),
            },
        )


async def retry_discord(
    operation: Callable[[], Awaitable[T]],
    *,
    retries: int = 2,
    base_delay: float = 0.5,
) -> T:
    """Retry transient Discord 5xx errors with bounded jittered backoff."""
    attempt = 0
    while True:
        try:
            return await operation()
        except (discord.NotFound, discord.Forbidden):
            raise
        except discord.HTTPException as ex:
            if ex.status < 500 or attempt >= retries:
                raise
            delay = base_delay * (2**attempt) + random.uniform(0.0, 0.25)
            attempt += 1
            await asyncio.sleep(delay)


async def send_role_ping(channel: discord.TextChannel, text: str) -> discord.Message:
    """Send a role-mention message to a text channel with bounded Discord retries."""
    mentions = discord.AllowedMentions(roles=True)

    async def _send() -> discord.Message:
        return await channel.send(text, allowed_mentions=mentions)

    return await retry_discord(_send)


async def handle_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> None:
    """Global error handler for application commands."""
    root_error: BaseException = getattr(error, "original", error)
    if isinstance(root_error, Oops):
        await safe_reply(interaction, f"❌ {root_error}", ephemeral=True)
        return
    if isinstance(error, app_commands.CheckFailure):
        await safe_reply(interaction, "⛔ You don't have permission to use this.", ephemeral=True)
        return

    error_id = new_error_id()
    logger.exception(
        "Unhandled application command error",
        exc_info=root_error,
        extra={
            "error_id": error_id,
            "guild_id": interaction.guild_id,
            "user_id": getattr(interaction.user, "id", None),
            "command": interaction.command.qualified_name if interaction.command else None,
        },
    )
    await safe_reply(
        interaction,
        f"⚠️ An unexpected error occurred (ref: `{error_id}`). Please try again.",
        ephemeral=True,
    )


class BaseView(discord.ui.View):
    """Base view with unified error logging and ephemeral timeout cleanup."""

    def __init__(self, *, timeout: float | None = None) -> None:
        super().__init__(timeout=timeout)
        self.ephemeral_message: discord.InteractionMessage | None = None

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any],
    ) -> None:
        if isinstance(error, Oops):
            await safe_reply(interaction, f"❌ {error}", ephemeral=True)
            return

        error_id = new_error_id()
        custom_id = getattr(item, "custom_id", None)
        logger.exception(
            "Unhandled view interaction error",
            exc_info=error,
            extra={
                "error_id": error_id,
                "guild_id": interaction.guild_id,
                "user_id": getattr(interaction.user, "id", None),
                "channel_id": interaction.channel_id,
                "custom_id": custom_id,
            },
        )
        await safe_reply(
            interaction,
            f"⚠️ Something went wrong processing that button (ref: `{error_id}`).",
            ephemeral=True,
        )

    async def on_timeout(self) -> None:
        if self.ephemeral_message is None:
            return
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        try:
            await self.ephemeral_message.edit(view=self)
        except discord.HTTPException:
            pass


class BaseModal(discord.ui.Modal):
    """Base modal with unified validation and unexpected error handling."""

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any] | None = None,
        /,
    ) -> None:
        if isinstance(error, Oops):
            await safe_reply(interaction, f"❌ {error}", ephemeral=True)
            return
        if isinstance(error, ValueError):
            await safe_reply(interaction, f"❌ {error}", ephemeral=True)
            return

        error_id = new_error_id()
        logger.exception(
            "Unhandled modal submission error",
            exc_info=error,
            extra={
                "error_id": error_id,
                "guild_id": interaction.guild_id,
                "user_id": getattr(interaction.user, "id", None),
                "channel_id": interaction.channel_id,
                "custom_id": self.custom_id,
            },
        )
        await safe_reply(
            interaction,
            f"⚠️ Something went wrong submitting the form (ref: `{error_id}`).",
            ephemeral=True,
        )
