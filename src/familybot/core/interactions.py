"""Discord interaction helpers shared across cogs."""

from __future__ import annotations

import discord

from familybot.core.errors import UserInputError
from familybot.core.logging import get_correlation_id, new_correlation_id
from familybot.core.permissions import ActorContext

SAFE_ALLOWED_MENTIONS = discord.AllowedMentions.none()


def build_actor_context(interaction: discord.Interaction) -> ActorContext:
    """Extract an ActorContext from a guild Discord interaction."""
    if interaction.guild_id is None:
        raise UserInputError("This command can only be used inside a server.")

    cid = get_correlation_id() or new_correlation_id()
    user = interaction.user
    role_ids: tuple[int, ...] = ()
    is_guild_admin = False

    if isinstance(user, discord.Member):
        role_ids = tuple(role.id for role in user.roles)
        is_guild_admin = bool(
            user.guild_permissions.administrator or user.guild_permissions.manage_guild
        )

    return ActorContext(
        guild_id=interaction.guild_id,
        discord_id=user.id,
        display_name=user.display_name,
        role_ids=role_ids,
        is_guild_admin=is_guild_admin,
        correlation_id=cid,
    )
