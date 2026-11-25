"""Business logic for the Cow Shed module (no discord imports)."""

from __future__ import annotations

from datetime import timedelta

from familybot.core.permissions import ActorContext, RoleLevel, require_role_level
from familybot.core.time import utcnow
from familybot.db.repositories.cow_shed_state import CowShedStateRecord
from familybot.db.repositories.protocols import UnitOfWorkFactory
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
                last_reminder_at=None,
            )
            await uow.commit()
            return self._dto(state)

    async def status(self, actor: ActorContext) -> CowShedDTO:
        async with self._uow_factory.open() as uow:
            state = await uow.cow_shed_state.get_or_create(actor.guild_id)
            await uow.commit()
            return self._dto(state)

    async def set_collect_role(self, actor: ActorContext, *, role_id: int) -> CowShedDTO:
        async with self._uow_factory.open() as uow:
            settings = await uow.guild_settings.get_or_create(actor.guild_id)
            require_role_level(actor, settings.role_map, RoleLevel.ADMIN, action="set collect role")
            state = await uow.cow_shed_state.update(actor.guild_id, collect_role_id=role_id)
            await uow.commit()
            return self._dto(state)

    async def stop_reminders(self, actor: ActorContext) -> CowShedDTO:
        async with self._uow_factory.open() as uow:
            settings = await uow.guild_settings.get_or_create(actor.guild_id)
            require_role_level(actor, settings.role_map, RoleLevel.ADMIN, action="stop reminders")
            state = await uow.cow_shed_state.update(actor.guild_id, reminders_active=False)
            await uow.commit()
            return self._dto(state)

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
    def _dto(state: CowShedStateRecord) -> CowShedDTO:
        return CowShedDTO(
            fed_at=state.fed_at,
            collect_at=state.collect_at,
            collect_due=(state.collect_at is not None and utcnow() >= state.collect_at),
        )
