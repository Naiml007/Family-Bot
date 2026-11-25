"""Pure-Python permission model and role checks used by the service layer."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum

from familybot.core.errors import AccessDeniedError


class RoleLevel(IntEnum):
    """Ordered family permission tiers."""

    MEMBER = 1
    ADMIN = 2
    LEADER = 3


@dataclass(frozen=True, slots=True)
class ActorContext:
    """Plain representation of the Discord actor invoking a service operation."""

    guild_id: int
    discord_id: int
    display_name: str
    role_ids: tuple[int, ...] = ()
    is_guild_admin: bool = False
    correlation_id: str = ""


def resolve_role_level(
    actor: ActorContext,
    role_map: Mapping[str, int | list[int]],
) -> RoleLevel:
    """Determine an actor's effective RoleLevel from guild_settings.role_map."""
    if actor.is_guild_admin:
        return RoleLevel.LEADER

    actor_roles = set(actor.role_ids)
    for key, level in (
        ("leader", RoleLevel.LEADER),
        ("admin", RoleLevel.ADMIN),
        ("member", RoleLevel.MEMBER),
    ):
        configured = role_map.get(key)
        if isinstance(configured, int) and configured in actor_roles:
            return level
        if isinstance(configured, list) and any(rid in actor_roles for rid in configured):
            return level

    return RoleLevel.MEMBER


def require_role_level(
    actor: ActorContext,
    role_map: Mapping[str, int | list[int]],
    minimum: RoleLevel,
    *,
    action: str = "perform this action",
) -> RoleLevel:
    """Verify actor meets the minimum RoleLevel or raise AccessDeniedError."""
    actual = resolve_role_level(actor, role_map)
    if actual < minimum:
        raise AccessDeniedError(f"You need `{minimum.name.title()}` permissions to {action}.")
    return actual
