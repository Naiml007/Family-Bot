import asyncio
from datetime import datetime

from thesnow.core.scheduler import DeadlineScheduler, next_deadline, next_fixed_schedule
from thesnow.shared.time import UK


def test_next_fixed_schedule_uses_uk_plantation_slot() -> None:
    timestamp = datetime(2026, 11, 27, 12, 0, tzinfo=UK).timestamp()
    deadline = datetime.fromtimestamp(next_fixed_schedule(timestamp), UK)

    assert deadline.hour == 12
    assert deadline.minute == 30


def test_next_deadline_is_earliest_persisted_work() -> None:
    timestamp = datetime(2026, 11, 27, 12, 0, tzinfo=UK).timestamp()
    deadline = next_deadline(
        timestamp,
        reminder_times=[int(timestamp) + 900],
        event_times=[int(timestamp) + 300],
        alert_times=[int(timestamp) + 600],
        fixed_schedules_enabled=False,
    )

    assert deadline == timestamp + 300


def test_next_deadline_handles_overdue_and_idle() -> None:
    timestamp = 1_700_000_000.0
    assert (
        next_deadline(
            timestamp,
            reminder_times=[int(timestamp) - 10],
            event_times=[],
            alert_times=[],
            fixed_schedules_enabled=False,
        )
        == timestamp
    )
    assert (
        next_deadline(
            timestamp,
            reminder_times=[],
            event_times=[],
            alert_times=[],
            fixed_schedules_enabled=False,
        )
        is None
    )


async def test_deadline_scheduler_wakes_on_notify_and_survives_errors() -> None:
    calls: list[int] = []
    second_tick = asyncio.Event()

    async def tick(now_ts: int) -> float | None:
        calls.append(now_ts)
        if len(calls) == 1:
            raise RuntimeError("boom")
        second_tick.set()
        return None

    scheduler = DeadlineScheduler(tick)
    scheduler.start()
    await asyncio.sleep(0.05)
    scheduler.notify()
    await asyncio.wait_for(second_tick.wait(), timeout=1.0)
    await scheduler.stop()

    assert len(calls) >= 2
