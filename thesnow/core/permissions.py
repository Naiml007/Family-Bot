import logging
from enum import StrEnum

import discord

from .database import ConfigCache
from .errors import safe_reply

logger = logging.getLogger("thesnow.permissions")


class RolePolicy(StrEnum):
    """Authorization level required for an action."""

    ADMIN = "admin"
    DEPUTY = "deputy"
    STAFF = "staff"
    TICKET_OWNER_OR_STAFF = "ticket_owner_or_staff"
    MEMBER = "member"


ACTION_POLICIES: dict[str, RolePolicy] = {
    "admin:setup": RolePolicy.ADMIN,
    "admin:set_roles": RolePolicy.ADMIN,
    "admin:plantation_setup": RolePolicy.ADMIN,
    "admin:plantation_stop": RolePolicy.ADMIN,
    "balance:deposit": RolePolicy.STAFF,
    "balance:withdraw": RolePolicy.STAFF,
    "balance:read": RolePolicy.MEMBER,
    "seeds:mutate": RolePolicy.STAFF,
    "solar:mutate": RolePolicy.STAFF,
    "armory:mutate": RolePolicy.STAFF,
    "storage:mutate": RolePolicy.STAFF,
    "storage:read": RolePolicy.MEMBER,
    "finance:mutate": RolePolicy.STAFF,
    "bonus:ticket_open": RolePolicy.MEMBER,
    "bonus:ticket_close": RolePolicy.TICKET_OWNER_OR_STAFF,
    "bonus:log": RolePolicy.DEPUTY,
    "schedule:ack": RolePolicy.STAFF,
    "reminders:manage": RolePolicy.STAFF,
    "reminders:read": RolePolicy.MEMBER,
    "events:manage": RolePolicy.STAFF,
    "events:read": RolePolicy.MEMBER,
}


class PermissionService:
    """Single source of truth for guild, role, and reaction authorization."""

    def __init__(self, config: ConfigCache, allowed_guild_ids: frozenset[int] = frozenset()) -> None:
        self.config = config
        self.allowed_guild_ids = allowed_guild_ids

    def is_guild_allowed(self, guild_id: int | None) -> bool:
        """Return True if guild_id is permitted under ALLOWED_GUILD_IDS."""
        if guild_id is None:
            return False
        if not self.allowed_guild_ids:
            return True
        return guild_id in self.allowed_guild_ids

    async def _staff_role_ids(self, guild_id: int, policy: RolePolicy) -> set[int]:
        keys = ("deputy_role",) if policy == RolePolicy.DEPUTY else ("mod_role", "deputy_role")
        values = await self.config.get_many(guild_id, *keys)
        role_ids: set[int] = set()
        for raw in values.values():
            if raw and raw.isdigit():
                role_ids.add(int(raw))
        return role_ids

    async def authorize(
        self,
        interaction: discord.Interaction,
        action: str,
        *,
        ticket_owner_id: int | None = None,
    ) -> bool:
        """Enforce default-deny authorization for an interaction action."""
        policy = ACTION_POLICIES.get(action)
        guild_id = interaction.guild_id
        user = interaction.user
        if policy is None or not self.is_guild_allowed(guild_id) or guild_id is None:
            logger.warning(
                "Permission denied (unknown action or disallowed guild)",
                extra={"guild_id": guild_id, "user_id": getattr(user, "id", None), "action": action},
            )
            await safe_reply(interaction, "⛔ This server or action is not authorized.")
            return False

        if not isinstance(user, discord.Member):
            logger.warning(
                "Permission denied (non-member context)",
                extra={"guild_id": guild_id, "user_id": getattr(user, "id", None), "action": action},
            )
            await safe_reply(interaction, "⛔ This action can only be used inside a server.")
            return False

        if policy == RolePolicy.MEMBER:
            return True

        if user.guild_permissions.administrator:
            return True

        if policy == RolePolicy.ADMIN:
            logger.warning(
                "Permission denied (administrator required)",
                extra={"guild_id": guild_id, "user_id": user.id, "action": action},
            )
            await safe_reply(interaction, "⛔ Administrator permission is required.")
            return False

        if policy == RolePolicy.TICKET_OWNER_OR_STAFF and ticket_owner_id is not None and user.id == ticket_owner_id:
            return True

        allowed_ids = await self._staff_role_ids(guild_id, policy)
        if not allowed_ids:
            logger.warning(
                "Permission denied (bot roles not configured)",
                extra={"guild_id": guild_id, "user_id": user.id, "action": action},
            )
            await safe_reply(
                interaction,
                "⛔ Bot roles are not configured yet; ask an Administrator to run `/set_roles`.",
            )
            return False

        if any(role.id in allowed_ids for role in user.roles):
            return True

        logger.warning(
            "Permission denied (missing required role)",
            extra={"guild_id": guild_id, "user_id": user.id, "action": action},
        )
        needed = "Deputy" if policy == RolePolicy.DEPUTY else "Moderator or Deputy"
        await safe_reply(interaction, f"⛔ You need the **{needed}** role to use this.")
        return False

    async def authorize_reaction_member(
        self,
        guild: discord.Guild,
        payload: discord.RawReactionActionEvent,
    ) -> discord.Member | None:
        """Resolve and verify a reactor member fail-closed against STAFF role policy."""
        if not self.is_guild_allowed(guild.id):
            return None

        member: discord.Member | None = payload.member or guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.warning(
                    "Reaction ack denied (could not resolve member)",
                    extra={"guild_id": guild.id, "user_id": payload.user_id, "action": "schedule:ack"},
                )
                return None

        if member.guild_permissions.administrator:
            return member

        allowed_ids = await self._staff_role_ids(guild.id, RolePolicy.STAFF)
        if allowed_ids and any(role.id in allowed_ids for role in member.roles):
            return member

        logger.warning(
            "Reaction ack denied (missing required role)",
            extra={"guild_id": guild.id, "user_id": member.id, "action": "schedule:ack"},
        )
        return None
