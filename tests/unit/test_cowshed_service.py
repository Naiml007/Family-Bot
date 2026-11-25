"""Unit tests for the Cow Shed service."""

from __future__ import annotations

from tests.unit.fakes import FakeUnitOfWorkFactory

from familybot.core.permissions import ActorContext
from familybot.modules.cowshed.service import CowshedService


def _actor() -> ActorContext:
    return ActorContext(guild_id=7, discord_id=77, display_name="Cow", is_guild_admin=True)


async def test_feed_sets_collect_time() -> None:
    factory = FakeUnitOfWorkFactory()
    service = CowshedService(factory)

    state = await service.feed(_actor())

    assert state.collect_at is not None
    assert state.collect_due is False
    assert factory.cow_shed_store[7].collect_at is not None


async def test_collect_reports_due_only_when_time_passed() -> None:
    factory = FakeUnitOfWorkFactory()
    service = CowshedService(factory)
    await service.feed(_actor())

    not_due = await service.collect(7)
    assert not_due.due is False
