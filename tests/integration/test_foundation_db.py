"""Integration tests for Phase 0 persistence against real PostgreSQL."""

from __future__ import annotations

import pytest

from familybot.core.permissions import ActorContext
from familybot.db.uow import SqlUnitOfWorkFactory
from familybot.modules.admin.schemas import RuntimeSnapshot
from familybot.modules.admin.service import AdminService


class _StubProbe:
    def get_runtime_snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            uptime_seconds=1.0,
            ws_latency_ms=10.0,
            loaded_modules=("admin",),
            version="0.1.0",
            git_sha=None,
        )

    async def ping_database(self) -> float | None:
        return 1.0


@pytest.mark.integration
async def test_admin_service_persists_guild_settings_and_audit_log(
    pg_uow_factory: SqlUnitOfWorkFactory,
) -> None:
    service = AdminService(pg_uow_factory, _StubProbe())
    actor = ActorContext(
        guild_id=987654321,
        discord_id=123456789,
        display_name="IntegrationOwner",
        is_guild_admin=True,
        correlation_id="it-ref-001",
    )

    updated = await service.update_config(actor, timezone="UTC", log_channel_id=555666)
    assert updated.timezone == "UTC"
    assert updated.log_channel_id == 555666

    tz_name, entries = await service.debug_correlation_id(actor, correlation_id="it-ref-001")
    assert tz_name == "UTC"
    assert any(e.action == "guild_config.updated" for e in entries)
