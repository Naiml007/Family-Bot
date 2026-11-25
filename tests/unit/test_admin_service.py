"""Unit tests for AdminService using fake UoW and RuntimeProbe."""

from __future__ import annotations

import pytest
from tests.unit.fakes import FakeRuntimeProbe, FakeUnitOfWorkFactory

from familybot.core.errors import AccessDeniedError, UserInputError
from familybot.core.permissions import ActorContext
from familybot.modules.admin.service import AdminService


def _leader_actor(cid: str = "cid-1") -> ActorContext:
    return ActorContext(
        guild_id=42,
        discord_id=1001,
        display_name="Leader",
        is_guild_admin=True,
        correlation_id=cid,
    )


def _member_actor(cid: str = "cid-2") -> ActorContext:
    return ActorContext(
        guild_id=42,
        discord_id=1002,
        display_name="Member",
        role_ids=(500,),
        is_guild_admin=False,
        correlation_id=cid,
    )


async def test_get_status_returns_runtime_metrics_and_enforces_admin() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    service = AdminService(uow_factory, FakeRuntimeProbe())

    status = await service.get_status(_leader_actor())
    assert status.uptime_seconds == 125.0
    assert status.ws_latency_ms == 42.0
    assert status.db_latency_ms == 1.5
    assert status.loaded_modules == ("admin", "solar")
    assert status.version == "0.1.0"

    with pytest.raises(AccessDeniedError):
        await service.get_status(_member_actor())


async def test_update_config_writes_audit_log_and_validates_timezone() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    service = AdminService(uow_factory, FakeRuntimeProbe())

    cfg = await service.update_config(
        _leader_actor("ref-cfg"),
        timezone="UTC",
        log_channel_id=9001,
        admin_role_id=700,
    )
    assert cfg.timezone == "UTC"
    assert cfg.log_channel_id == 9001
    assert cfg.role_map == {"admin": 700}

    assert len(uow_factory.audit_store) == 1
    audit = uow_factory.audit_store[0]
    assert audit.action == "guild_config.updated"
    assert audit.correlation_id == "ref-cfg"

    # Admin (non-leader) cannot reassign role_map
    admin_actor = ActorContext(
        guild_id=42,
        discord_id=1003,
        display_name="Admin",
        role_ids=(700,),
        is_guild_admin=False,
        correlation_id="ref-admin",
    )
    with pytest.raises(AccessDeniedError):
        await service.update_config(admin_actor, leader_role_id=700)

    with pytest.raises(UserInputError):
        await service.update_config(_leader_actor(), timezone="Invalid/Zone")


async def test_set_module_enabled_protects_admin_and_audits() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    service = AdminService(uow_factory, FakeRuntimeProbe())

    with pytest.raises(UserInputError):
        await service.set_module_enabled(_leader_actor(), module_name="admin", enabled=False)

    with pytest.raises(UserInputError):
        await service.set_module_enabled(_leader_actor(), module_name="nonexistent", enabled=True)

    cfg = await service.set_module_enabled(
        _leader_actor("ref-mod"), module_name="solar", enabled=False
    )
    assert cfg.enabled_modules["solar"] is False
    assert uow_factory.audit_store[-1].action == "module.disabled"


async def test_debug_and_recent_logs_queries() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    service = AdminService(uow_factory, FakeRuntimeProbe())

    await service.update_config(_leader_actor("trace-abc"), log_channel_id=111)
    await service.set_module_enabled(_leader_actor("trace-xyz"), module_name="solar", enabled=True)

    _, matching = await service.debug_correlation_id(_leader_actor(), correlation_id="trace-abc")
    assert len(matching) == 1
    assert matching[0].action == "guild_config.updated"

    _, recent = await service.list_recent_logs(_leader_actor(), limit=5)
    assert len(recent) == 2
    assert recent[0].correlation_id == "trace-xyz"

    with pytest.raises(UserInputError):
        await service.list_recent_logs(_leader_actor(), limit=100)


async def test_permission_check_runs_before_timezone_validation() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    service = AdminService(uow_factory, FakeRuntimeProbe())

    with pytest.raises(AccessDeniedError):
        await service.update_config(_member_actor(), timezone="../etc/passwd")


@pytest.mark.parametrize("timezone", ["x" * 65, "../etc/passwd"])
async def test_update_config_bounds_and_validates_timezone(timezone: str) -> None:
    uow_factory = FakeUnitOfWorkFactory()
    service = AdminService(uow_factory, FakeRuntimeProbe())

    with pytest.raises(UserInputError):
        await service.update_config(_leader_actor(), timezone=timezone)


async def test_debug_rejects_overlong_reference() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    service = AdminService(uow_factory, FakeRuntimeProbe())

    with pytest.raises(UserInputError):
        await service.debug_correlation_id(_leader_actor(), correlation_id="x" * 65)


async def test_set_module_enabled_rejects_unknown_module_without_loaded_modules() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    service = AdminService(uow_factory, FakeRuntimeProbe(loaded_modules=()))

    with pytest.raises(UserInputError):
        await service.set_module_enabled(_leader_actor(), module_name="solar", enabled=True)
