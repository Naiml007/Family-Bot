"""Business logic for the Cow Shed module (no discord imports)."""

from __future__ import annotations

from datetime import timedelta

from familybot.core.permissions import ActorContext, RoleLevel, require_role_level
from familybot.core.time import utcnow
from familybot.db.repositories.cow_shed_state import CowShedStateRecord
from familybot.db.repositories.protocols import GuildSettingsRecord, UnitOfWorkFactory
from familybot.modules.cowshed.schemas import CollectResult, CowShedDTO


class CowshedService:
    """Track feeding time and compute the next milk-collection deadline."""

    COLLECT_DELAY = timedelta(hours=3)

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def feed(self, actor: ActorContext) -> CowShedDTO:
        async with self._uow_factory.open() as uow:
            settings = await uow.guild_settings.get_or_create(actor.guild_id)
            require_role_level(actor, settings.role_map, RoleLevel.ADMIN, action="feed cows")
            now = utcnow()
            state = await uow.cow_shed_state.update(
                actor.guild_id,
                fed_at=now,
                collect_at=now + type(self).COLLECT_DELAY,
                reminders_active=True,
            )
            await uow.commit()
            return self._dto(state, settings)

    async def status(self, actor: ActorContext) -> CowShedDTO:
        async with self._uow_factory.open() as uow:
            settings = await uow.guild_settings.get_or_create(actor.guild_id)
            state = await uow.cow_shed_state.get_or_create(actor.guild_id)
            await uow.commit()
            return self._dto(state, settings)

    async def set_collect_role(self, actor: ActorContext, *, role_id: int) -> CowShedDTO:
        async with self._uow_factory.open() as uow:
            settings = await uow.guild_settings.get_or_create(actor.guild_id)
            require_role_level(actor, settings.role_map, RoleLevel.ADMIN, action="set collect role")
            state = await uow.cow_shed_state.update(actor.guild_id, collect_role_id=role_id)
            await uow.commit()
            return self._dto(state, settings)

    async def set_reminders_channel(self, actor: ActorContext, *, channel_id: int) -> None:
        async with self._uow_factory.open() as uow:
            settings = await uow.guild_settings.get_or_create(actor.guild_id)
            require_role_level(
                actor, settings.role_map, RoleLevel.ADMIN, action="set reminders channel"
            )
            await uow.guild_settings.update(actor.guild_id, reminders_channel_id=channel_id)
            await uow.commit()

    async def set_reminder_message(self, guild_id: int, message_id: int) -> None:
        async with self._uow_factory.open() as uow:
            await uow.cow_shed_state.update(guild_id, reminder_message_id=message_id)
            await uow.commit()

    async def stop_reminders(self, actor: ActorContext) -> CowShedDTO:
        async with self._uow_factory.open() as uow:
            settings = await uow.guild_settings.get_or_create(actor.guild_id)
            require_role_level(actor, settings.role_map, RoleLevel.ADMIN, action="stop reminders")
            state = await uow.cow_shed_state.update(actor.guild_id, reminders_active=False)
            await uow.commit()
            return self._dto(state, settings)

    async def collect(self, guild_id: int) -> CollectResult:
        async with self._uow_factory.open() as uow:
            state = await uow.cow_shed_state.get_or_create(guild_id)
            due = state.collect_at is not None and utcnow() >= state.collect_at
            await uow.commit()
            return CollectResult(
                due=due,
                collect_at=state.collect_at,
                collect_role_id=state.collect_role_id,
            )

    @staticmethod
    def _dto(state: CowShedStateRecord, settings: GuildSettingsRecord) -> CowShedDTO:
        return CowShedDTO(
            fed_at=state.fed_at,
            collect_at=state.collect_at,
            collect_due=(state.collect_at is not None and utcnow() >= state.collect_at),
            reminders_channel_id=settings.reminders_channel_id,
            reminder_message_id=state.reminder_message_id,
            last_reminder_at=state.last_reminder_at,
        )
