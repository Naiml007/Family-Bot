from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .constants import COW_HOURS

UK = ZoneInfo("Europe/London")


def uk_str(timestamp: float) -> str:
    """Format a Unix timestamp in Europe/London display format."""
    return datetime.fromtimestamp(timestamp, UK).strftime("%d %b %Y, %H:%M %Z")


def uk_today(now_ts: float | None = None) -> str:
    """Return the current YYYY-MM-DD date string in Europe/London."""
    dt = datetime.fromtimestamp(now_ts, UK) if now_ts is not None else datetime.now(UK)
    return dt.strftime("%Y-%m-%d")


def uk_day_start_ts(now_ts: float | None = None) -> int:
    """Return the Unix timestamp for midnight at the start of the current UK day."""
    now = datetime.fromtimestamp(now_ts, UK) if now_ts is not None else datetime.now(UK)
    return int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def format_slot_key(slot_ts: int) -> str:
    """Build a DST-unambiguous UK slot key storing date, hour:minute, and UTC offset."""
    dt = datetime.fromtimestamp(slot_ts, UK)
    offset = dt.strftime("%z") or "+0000"
    return f"{dt:%Y-%m-%d-%H:%M}{offset}"


def slot_label_from_key(slot_key: str) -> str:
    """Extract a human-readable HH:MM label from both legacy and offset-qualified slot keys."""
    tail = slot_key.split("-")[-1]
    if "+" in tail:
        return tail.split("+", 1)[0]
    return tail


def _iter_cow_slot_timestamps(now_ts: float) -> list[int]:
    """Enumerate valid UK cow-shed timestamps around now, filtering non-existent DST wall times."""
    center = datetime.fromtimestamp(now_ts, UK).date()
    timestamps: list[int] = []
    for day_offset in (-1, 0, 1, 2):
        day = center + timedelta(days=day_offset)
        for hour in COW_HOURS:
            for fold in (0, 1):
                candidate = datetime(day.year, day.month, day.day, hour, 0, tzinfo=UK, fold=fold)
                ts = int(candidate.timestamp())
                round_trip = datetime.fromtimestamp(ts, UK)
                if (round_trip.date(), round_trip.hour, round_trip.minute, round_trip.fold) == (day, hour, 0, fold):
                    timestamps.append(ts)
    return sorted(set(timestamps))


def next_cow_slot(now_ts: float) -> tuple[int, str]:
    """Return (timestamp, 'HH:MM UK') for the next cowshed schedule strictly after now_ts."""
    for ts in _iter_cow_slot_timestamps(now_ts):
        if ts > now_ts:
            label = datetime.fromtimestamp(ts, UK).strftime("%H:%M UK")
            return ts, label
    raise RuntimeError("No upcoming cowshed schedule slot found")  # pragma: no cover


def latest_due_cow_slot(now_ts: float, grace_seconds: int) -> tuple[int, str, str] | None:
    """Return (slot_ts, slot_key, hhmm_label) if a cowshed slot is within grace_seconds of now_ts."""
    now_int = int(now_ts)
    due = [ts for ts in _iter_cow_slot_timestamps(now_ts) if ts <= now_int]
    if not due:
        return None
    latest = due[-1]
    if now_int - latest > grace_seconds:
        return None
    dt = datetime.fromtimestamp(latest, UK)
    return latest, format_slot_key(latest), dt.strftime("%H:%M")


def next_plant_slot(now_ts: float) -> tuple[int, str]:
    """Return (timestamp, 'HH:MM UK') for the next hourly :30 UK plantation slot strictly after now_ts."""
    # Europe/London offset is always whole hours (UTC+0 or UTC+1), so every UK :30 slot
    # falls exactly on UTC :30 regardless of DST transitions.
    now_int = int(now_ts)
    latest = ((now_int - 1800) // 3600) * 3600 + 1800
    nxt = latest + 3600
    label = datetime.fromtimestamp(nxt, UK).strftime("%H:%M UK")
    return nxt, label


def latest_due_plant_slot(now_ts: float, grace_seconds: int) -> tuple[int, str, str] | None:
    """Return (slot_ts, slot_key, hhmm_label) if a plantation :30 slot is within grace_seconds of now_ts."""
    now_int = int(now_ts)
    latest = ((now_int - 1800) // 3600) * 3600 + 1800
    if now_int - latest > grace_seconds:
        return None
    dt = datetime.fromtimestamp(latest, UK)
    return latest, format_slot_key(latest), dt.strftime("%H:%M")


def next_fixed_uk_ts(now_ts: float) -> int:
    """Return the earliest upcoming cowshed or plantation schedule timestamp strictly after now_ts."""
    cow_ts, _ = next_cow_slot(now_ts)
    plant_ts, _ = next_plant_slot(now_ts)
    return min(cow_ts, plant_ts)


def parse_uk_hhmm(time_text: str, now_ts: float | None = None) -> int:
    """Parse HH:MM in UK time into the next matching Unix timestamp."""
    parts = time_text.strip().split(":")
    if len(parts) != 2:
        raise ValueError("Time must be formatted as HH:MM")
    hour, minute = int(parts[0]), int(parts[1])
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Hour must be 00-23 and minute 00-59")

    ref_utc = (
        datetime.fromtimestamp(now_ts, UTC)
        if now_ts is not None
        else datetime.now(UTC)
    )
    now_uk = ref_utc.astimezone(UK)
    for day_offset in (0, 1, 2):
        day = now_uk.date() + timedelta(days=day_offset)
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=UK)
        ts = int(candidate.timestamp())
        round_trip = datetime.fromtimestamp(ts, UK)
        if (round_trip.date(), round_trip.hour, round_trip.minute) == (day, hour, minute) and ts > int(
            ref_utc.timestamp()
        ):
            return ts
    raise ValueError("Could not resolve next UK timestamp")  # pragma: no cover


def parse_uk_event_datetime(date_text: str, time_text: str) -> int:
    """Parse DD/MM/YYYY and HH:MM in UK time into a Unix timestamp."""
    parsed = datetime.strptime(f"{date_text.strip()} {time_text.strip()}", "%d/%m/%Y %H:%M")
    candidate = parsed.replace(tzinfo=UK)
    ts = int(candidate.timestamp())
    round_trip = datetime.fromtimestamp(ts, UK)
    if (round_trip.year, round_trip.month, round_trip.day, round_trip.hour, round_trip.minute) != (
        parsed.year,
        parsed.month,
        parsed.day,
        parsed.hour,
        parsed.minute,
    ):
        raise ValueError("Invalid UK local time during DST transition")
    return ts
