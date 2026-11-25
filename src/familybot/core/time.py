"""Timezone-aware UTC helpers, guild formatting, and duration parsing."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from familybot.core.errors import UserInputError

_DURATION_PART_RE = re.compile(r"(\d+)\s*([dhms])", re.IGNORECASE)
_MAX_DURATION_INPUT = 32
_MAX_DURATION_SECONDS = 31_536_000
_UNIT_SECONDS = {
    "d": 86_400,
    "h": 3_600,
    "m": 60,
    "s": 1,
}


def utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def validate_timezone(tz_name: str) -> ZoneInfo:
    """Validate an IANA timezone name or raise UserInputError."""
    if not tz_name or len(tz_name) > 64:
        raise UserInputError("Provide an IANA timezone name of at most 64 characters.")
    try:
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise UserInputError(
            f"Unknown timezone `{tz_name}`. Use an IANA name like `UTC` or `America/New_York`."
        ) from exc


def format_dt(dt: datetime, tz_name: str = "UTC") -> str:
    """Format a UTC datetime in the configured guild timezone."""
    tz = validate_timezone(tz_name)
    localized = ensure_utc(dt).astimezone(tz)
    return localized.strftime("%Y-%m-%d %H:%M:%S %Z")


def parse_duration(raw: str) -> int:
    """Parse a human duration such as `1h30m`, `45m`, or `90s` into positive seconds."""
    cleaned = raw.strip()
    if not cleaned or len(cleaned) > _MAX_DURATION_INPUT:
        raise UserInputError("Duration cannot be empty or longer than 32 characters.")

    if cleaned.isdigit():
        seconds = int(cleaned)
        if seconds <= 0:
            raise UserInputError("Duration must be greater than 0 seconds.")
        if seconds > _MAX_DURATION_SECONDS:
            raise UserInputError("Duration exceeds the maximum of one year (365 days).")
        return seconds

    pos = 0
    total = 0
    for match in _DURATION_PART_RE.finditer(cleaned):
        gap = cleaned[pos : match.start()]
        if gap.strip():
            raise UserInputError(f"Invalid duration `{raw}`. Examples: `30m`, `2h`, `1h30m`.")
        pos = match.end()
        value = int(match.group(1))
        unit = match.group(2).lower()
        total += value * _UNIT_SECONDS[unit]

    if pos == 0 or cleaned[pos:].strip():
        raise UserInputError(f"Invalid duration `{raw}`. Examples: `30m`, `2h`, `1h30m`.")
    if total <= 0:
        raise UserInputError("Duration must be greater than 0 seconds.")
    if total > _MAX_DURATION_SECONDS:
        raise UserInputError("Duration exceeds the maximum of one year (365 days).")
    return total
