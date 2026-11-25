"""Unit tests for core.time helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from familybot.core.errors import UserInputError
from familybot.core.time import ensure_utc, format_dt, parse_duration, validate_timezone


def test_ensure_utc_normalizes_naive_and_offset_datetimes() -> None:
    naive = datetime(2026, 11, 25, 12, 0, 0)
    assert ensure_utc(naive) == datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)

    plus_two = datetime(2026, 11, 25, 14, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    assert ensure_utc(plus_two) == datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)


def test_format_dt_uses_guild_timezone() -> None:
    dt = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)
    formatted = format_dt(dt, "UTC")
    assert formatted == "2026-11-25 12:00:00 UTC"


def test_validate_timezone_rejects_unknown_name() -> None:
    with pytest.raises(UserInputError):
        validate_timezone("Mars/Olympus_Mons")


@pytest.mark.parametrize(
    "raw",
    ["", "../etc/passwd", "/etc/passwd", "a/../b"],
)
def test_validate_timezone_rejects_path_like_names(raw: str) -> None:
    with pytest.raises(UserInputError):
        validate_timezone(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("45s", 45),
        ("10m", 600),
        ("1h30m", 5400),
        ("1d 2h 3m 4s", 93784),
        ("120", 120),
    ],
)
def test_parse_duration_happy_paths(raw: str, expected: int) -> None:
    assert parse_duration(raw) == expected


@pytest.mark.parametrize("raw", ["", "0s", "-5m", "abc", "10m junk"])
def test_parse_duration_invalid_inputs(raw: str) -> None:
    with pytest.raises(UserInputError):
        parse_duration(raw)
