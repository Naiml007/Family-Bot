import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Sequence

from thesnow.shared.time import next_fixed_uk_ts

logger = logging.getLogger("thesnow.scheduler")

MAX_SLEEP_SECONDS = 86_400.0


def next_fixed_schedule(timestamp: float) -> float:
    """Return the earliest upcoming cowshed or plantation UK schedule timestamp."""
    return float(next_fixed_uk_ts(timestamp))


def next_deadline(
    timestamp: float,
    reminder_times: Sequence[int],
    event_times: Sequence[int],
    alert_times: Sequence[int],
    fixed_schedules_enabled: bool = True,
    next_fixed_ts: float | None = None,
) -> float | None:
    """Compute the earliest next wakeup timestamp, or None when idle with no work."""
    all_times = (*reminder_times, *event_times, *alert_times)
    if any(value <= timestamp for value in all_times):
        return float(timestamp)

    deadlines: list[float] = [float(value) for value in all_times if value > timestamp]
    if fixed_schedules_enabled:
        deadlines.append(next_fixed_ts if next_fixed_ts is not None else next_fixed_schedule(timestamp))

    return min(deadlines) if deadlines else None


class DeadlineScheduler:
    """Event-driven deadline scheduler with zero idle polling and supervised lifecycle."""

    def __init__(self, tick_handler: Callable[[int], Awaitable[float | None]]) -> None:
        self._tick_handler = tick_handler
        self._wake_event = asyncio.Event()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def notify(self) -> None:
        """Wake the scheduler immediately after a reminder, event, or schedule mutation."""
        self._wake_event.set()

    def start(self) -> None:
        """Start the supervised background scheduler task if not already running."""
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._wake_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="thesnow-scheduler")
        self._task.add_done_callback(self._on_task_done)

    async def stop(self) -> None:
        """Signal shutdown and await clean scheduler task termination."""
        self._stop_event.set()
        self._wake_event.set()
        if self._task is not None:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def _on_task_done(self, task: asyncio.Task[None]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Scheduler task crashed unexpectedly", exc_info=exc)

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self._wake_event.clear()
            now_ts = int(time.time())
            try:
                deadline = await self._tick_handler(now_ts)
            except Exception as ex:
                logger.exception("Scheduler tick failed", exc_info=ex)
                deadline = float(now_ts + 60)

            if self._stop_event.is_set():
                break

            if deadline is None:
                await self._wake_event.wait()
                continue

            delay = max(0.0, deadline - time.time())
            if delay == 0.0 and not self._wake_event.is_set():
                # Avoid a tight zero-delay spin if a failing job kept its deadline <= now.
                delay = 1.0
            timeout = min(delay, MAX_SLEEP_SECONDS)
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=timeout)
            except TimeoutError:
                pass
