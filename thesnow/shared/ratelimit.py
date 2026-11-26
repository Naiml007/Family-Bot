import time


class UserCooldown:
    """Bounded per-(guild, user, action) sliding cooldown tracker."""

    def __init__(self, cooldown_seconds: float, *, max_entries: int = 4096) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.max_entries = max_entries
        self._last_used: dict[tuple[int, int, str], float] = {}

    def check_and_consume(self, guild_id: int, user_id: int, action: str, now: float | None = None) -> float:
        """Return 0.0 if allowed (and record timestamp), else remaining cooldown seconds."""
        current = now if now is not None else time.monotonic()
        self._prune(current)
        key = (guild_id, user_id, action)
        last = self._last_used.get(key)
        if last is not None:
            elapsed = current - last
            if elapsed < self.cooldown_seconds:
                return self.cooldown_seconds - elapsed
        self._last_used[key] = current
        return 0.0

    def _prune(self, current: float) -> None:
        cutoff = current - self.cooldown_seconds
        if len(self._last_used) >= self.max_entries:
            expired = [k for k, ts in self._last_used.items() if ts <= cutoff]
            for k in expired:
                del self._last_used[k]
            if len(self._last_used) >= self.max_entries:
                oldest = sorted(self._last_used.items(), key=lambda item: item[1])[: len(self._last_used) // 2]
                for k, _ in oldest:
                    del self._last_used[k]
