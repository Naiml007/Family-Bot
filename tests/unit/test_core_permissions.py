"""Unit tests for core.permissions role resolution."""

from __future__ import annotations

import pytest

from familybot.core.errors import AccessDeniedError
from familybot.core.permissions import (
    ActorContext,
    RoleLevel,
    require_role_level,
    resolve_role_level,
)


def test_guild_admin_resolves_to_leader() -> None:
    actor = ActorContext(
        guild_id=1,
        discord_id=10,
        display_name="Owner",
        role_ids=(),
        is_guild_admin=True,
        correlation_id="ref1",
    )
    assert resolve_role_level(actor, {}) == RoleLevel.LEADER


def test_role_map_resolves_admin_and_leader_roles() -> None:
    role_map: dict[str, int | list[int]] = {"leader": 100, "admin": [200, 201], "member": 300}

    admin_actor = ActorContext(guild_id=1, discord_id=11, display_name="Mod", role_ids=(201, 300))
    assert resolve_role_level(admin_actor, role_map) == RoleLevel.ADMIN

    member_actor = ActorContext(guild_id=1, discord_id=12, display_name="User", role_ids=(300,))
    assert resolve_role_level(member_actor, role_map) == RoleLevel.MEMBER


def test_require_role_level_raises_access_denied_when_insufficient() -> None:
    actor = ActorContext(guild_id=1, discord_id=12, display_name="User", role_ids=(300,))
    with pytest.raises(AccessDeniedError):
        require_role_level(actor, {"admin": 200}, RoleLevel.ADMIN, action="view status")
