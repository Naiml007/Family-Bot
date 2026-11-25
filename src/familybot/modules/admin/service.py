"""Business logic for the admin module (no discord imports)."""

from __future__ import annotations

from familybot.core.errors import UserInputError
from familybot.core.permissions import ActorContext, RoleLevel, require_role_level
from familybot.core.time import validate_timezone
from familybot.db.repositories.protocols import (
    AuditLogRecord,
    GuildSettingsRecord,
    UnitOfWorkFactory,
)
from familybot.modules.admin.schemas import (
    AuditEntryDTO,
    BotStatusDTO,
    GuildConfigDTO,
    RuntimeProbe,
)
from familybot.observability.audit import record_audit

_PROTECTED_MODULES = frozenset({"admin"})


def _to_config_dto(record: GuildSettingsRecord) -> GuildConfigDTO:
    return GuildConfigDTO(
        guild_id=record.guild_id,
        timezone=record.timezone,
        log_channel_id=record.log_channel_id,
        error_channel_id=record.error_channel_id,
        role_map=dict(record.role_map),
        enabled_modules=dict(record.enabled_modules),
        updated_at=record.updated_at,
    )


def _to_audit_dto(record: AuditLogRecord) -> AuditEntryDTO:
    return AuditEntryDTO(
        id=record.id,
        actor_id=record.actor_id,
        action=record.action,
        entity=record.entity,
        entity_id=record.entity_id,
        payload=dict(record.payload),
        correlation_id=record.correlation_id,
        created_at=record.created_at,
    )


class AdminService:
    """Handles admin diagnostics, configuration, module toggles, and audit queries."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        runtime_probe: RuntimeProbe,
    ) -> None:
        self._uow_factory = uow_factory
        self._probe = runtime_probe

    async def get_status(self, actor: ActorContext) -> BotStatusDTO:
        """Return bot health/runtime status; requires Admin role."""
        async with self._uow_factory.open() as uow:
            settings = await uow.guild_settings.get_or_create(actor.guild_id)
            require_role_level(
                actor,
                settings.role_map,
                RoleLevel.ADMIN,
                action="view bot status",
            )
            await uow.commit()

        snapshot = self._probe.get_runtime_snapshot()
        db_latency_ms = await self._probe.ping_database()
        return BotStatusDTO(
            uptime_seconds=snapshot.uptime_seconds,
            ws_latency_ms=snapshot.ws_latency_ms,
            db_latency_ms=db_latency_ms,
            pending_reminders=None,
            failed_reminders=None,
            loaded_modules=snapshot.loaded_modules,
            version=snapshot.version,
            git_sha=snapshot.git_sha,
        )

    async def get_config(self, actor: ActorContext) -> GuildConfigDTO:
        """Fetch current guild configuration; requires Admin role."""
        async with self._uow_factory.open() as uow:
            settings = await uow.guild_settings.get_or_create(actor.guild_id)
            require_role_level(
                actor,
                settings.role_map,
                RoleLevel.ADMIN,
                action="view guild configuration",
            )
            await uow.commit()
            return _to_config_dto(settings)

    async def update_config(
        self,
        actor: ActorContext,
        *,
        timezone: str | None = None,
        log_channel_id: int | None = None,
        error_channel_id: int | None = None,
        leader_role_id: int | None = None,
        admin_role_id: int | None = None,
        member_role_id: int | None = None,
    ) -> GuildConfigDTO:
        """Update guild settings (Leader required for role_map changes, Admin otherwise)."""
        if timezone is not None:
            validate_timezone(timezone)

        role_changes: dict[str, int] = {}
        if leader_role_id is not None:
            role_changes["leader"] = leader_role_id
        if admin_role_id is not None:
            role_changes["admin"] = admin_role_id
        if member_role_id is not None:
            role_changes["member"] = member_role_id

        required = RoleLevel.LEADER if role_changes else RoleLevel.ADMIN

        async with self._uow_factory.open() as uow:
            current = await uow.guild_settings.get_or_create(actor.guild_id)
            require_role_level(
                actor,
                current.role_map,
                required,
                action="update guild configuration",
            )

            next_role_map = dict(current.role_map)
            next_role_map.update(role_changes)

            updated = await uow.guild_settings.update(
                actor.guild_id,
                timezone=timezone,
                log_channel_id=log_channel_id,
                error_channel_id=error_channel_id,
                role_map=next_role_map if role_changes else None,
            )

            changed_fields: dict[str, object] = {}
            if timezone is not None:
                changed_fields["timezone"] = timezone
            if log_channel_id is not None:
                changed_fields["log_channel_id"] = log_channel_id
            if error_channel_id is not None:
                changed_fields["error_channel_id"] = error_channel_id
            if role_changes:
                changed_fields["role_map"] = role_changes

            await record_audit(
                uow,
                actor,
                action="guild_config.updated",
                entity="guild_settings",
                entity_id=str(actor.guild_id),
                payload=changed_fields,
            )
            await uow.commit()
            return _to_config_dto(updated)

    async def set_module_enabled(
        self,
        actor: ActorContext,
        *,
        module_name: str,
        enabled: bool,
    ) -> GuildConfigDTO:
        """Enable or disable a feature module for the guild."""
        normalized = module_name.strip().lower()
        if not normalized:
            raise UserInputError("Module name cannot be empty.")
        if not enabled and normalized in _PROTECTED_MODULES:
            raise UserInputError(f"Module `{normalized}` cannot be disabled.")

        snapshot = self._probe.get_runtime_snapshot()
        known = {m.lower() for m in snapshot.loaded_modules}
        if known and normalized not in known:
            available = ", ".join(sorted(known))
            raise UserInputError(f"Unknown module `{normalized}`. Loaded modules: {available}.")

        async with self._uow_factory.open() as uow:
            current = await uow.guild_settings.get_or_create(actor.guild_id)
            require_role_level(
                actor,
                current.role_map,
                RoleLevel.ADMIN,
                action="toggle modules",
            )
            modules = dict(current.enabled_modules)
            modules[normalized] = enabled
            updated = await uow.guild_settings.update(
                actor.guild_id,
                enabled_modules=modules,
            )
            await record_audit(
                uow,
                actor,
                action="module.enabled" if enabled else "module.disabled",
                entity="guild_settings",
                entity_id=str(actor.guild_id),
                payload={"module": normalized, "enabled": enabled},
            )
            await uow.commit()
            return _to_config_dto(updated)

    async def assert_admin(self, actor: ActorContext, *, action: str) -> GuildConfigDTO:
        """Verify admin access for runtime commands like sync/reload and return config."""
        async with self._uow_factory.open() as uow:
            settings = await uow.guild_settings.get_or_create(actor.guild_id)
            require_role_level(actor, settings.role_map, RoleLevel.ADMIN, action=action)
            await uow.commit()
            return _to_config_dto(settings)

    async def record_runtime_action(
        self,
        actor: ActorContext,
        *,
        action: str,
        entity_id: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        """Write an audit entry for runtime admin actions (reload, sync)."""
        async with self._uow_factory.open() as uow:
            await record_audit(
                uow,
                actor,
                action=action,
                entity="bot_runtime",
                entity_id=entity_id,
                payload=payload,
            )
            await uow.commit()

    async def debug_correlation_id(
        self, actor: ActorContext, *, correlation_id: str
    ) -> tuple[str, list[AuditEntryDTO]]:
        """Look up audit log rows matching a correlation ID."""
        cleaned = correlation_id.strip()
        if not cleaned:
            raise UserInputError("Provide a non-empty correlation reference ID.")

        async with self._uow_factory.open() as uow:
            settings = await uow.guild_settings.get_or_create(actor.guild_id)
            require_role_level(
                actor,
                settings.role_map,
                RoleLevel.ADMIN,
                action="inspect debug logs",
            )
            rows = await uow.audit_logs.find_by_correlation_id(actor.guild_id, cleaned)
            await uow.commit()
            return settings.timezone, [_to_audit_dto(row) for row in rows]

    async def list_recent_logs(
        self, actor: ActorContext, *, limit: int = 10
    ) -> tuple[str, list[AuditEntryDTO]]:
        """List recent audit log rows for the guild."""
        if limit < 1 or limit > 25:
            raise UserInputError("Limit must be between 1 and 25.")

        async with self._uow_factory.open() as uow:
            settings = await uow.guild_settings.get_or_create(actor.guild_id)
            require_role_level(
                actor,
                settings.role_map,
                RoleLevel.ADMIN,
                action="view audit logs",
            )
            rows = await uow.audit_logs.list_recent(actor.guild_id, limit=limit)
            await uow.commit()
            return settings.timezone, [_to_audit_dto(row) for row in rows]
