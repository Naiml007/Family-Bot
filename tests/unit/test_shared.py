from datetime import datetime

import pytest

from thesnow.shared.constants import MAX_AMOUNT
from thesnow.shared.ratelimit import UserCooldown
from thesnow.shared.time import (
    UK,
    latest_due_cow_slot,
    latest_due_plant_slot,
    next_cow_slot,
    next_plant_slot,
    parse_uk_event_datetime,
    parse_uk_hhmm,
    slot_label_from_key,
    uk_day_start_ts,
    uk_str,
    uk_today,
)
from thesnow.shared.validation import (
    Oops,
    bar,
    clip,
    is_allowed_discord_image_url,
    is_valid_image_attachment,
    normalize_item_name,
    normalize_plate,
    num,
    truncate_text,
)


def test_num_validates_bounds_and_formatting() -> None:
    assert num(" $1,250 ") == 1250
    assert num("#42") == 42
    assert num("0", zero=True) == 0

    with pytest.raises(ValueError):
        num("0", zero=False)
    with pytest.raises(ValueError):
        num("-5", zero=True)
    with pytest.raises(ValueError):
        num(str(MAX_AMOUNT + 1))
    with pytest.raises(ValueError):
        num("   ")


def test_clip_enforces_discord_char_budget() -> None:
    lines = [f"item-{i}: " + ("x" * 90) for i in range(25)]
    text = clip(lines, limit=25, max_chars=1024)
    assert len(text) <= 1024
    assert "…and " in text

    huge = clip(["a" * 2000], limit=5, max_chars=1024)
    assert len(huge) <= 1024
    assert huge.endswith("…")
    assert clip([], limit=5) == "—"
    assert truncate_text("hello", 3) == "he…"
    assert bar(5, 10, length=4) == "▰▰▱▱"


def test_validation_helpers() -> None:
    assert normalize_item_name("  heavy   rifle  ") == "Heavy Rifle"
    with pytest.raises(Oops):
        normalize_item_name("   ")

    assert normalize_plate("ab1") == "AB1"
    with pytest.raises(Oops):
        normalize_plate("12")

    assert is_valid_image_attachment("image/png", "shot.bin", 1024)
    assert is_valid_image_attachment(None, "photo.JPG", 512)
    assert not is_valid_image_attachment("text/plain", "notes.txt", 100)
    assert not is_valid_image_attachment("image/png", "huge.png", 10 * 1024 * 1024)

    assert is_allowed_discord_image_url("https://cdn.discordapp.com/attachments/1/2/proof.png")
    assert is_allowed_discord_image_url("attachment://proof.png")
    assert not is_allowed_discord_image_url("https://evil.example/tracker.png")
    assert not is_allowed_discord_image_url("http://cdn.discordapp.com/a.png")
    assert not is_allowed_discord_image_url("attachment://../secret.png")


def test_user_cooldown_prunes_and_enforces() -> None:
    cd = UserCooldown(30.0, max_entries=2)
    assert cd.check_and_consume(1, 10, "ticket:new", now=100.0) == 0.0
    rem = cd.check_and_consume(1, 10, "ticket:new", now=110.0)
    assert rem == pytest.approx(20.0)
    assert cd.check_and_consume(1, 20, "ticket:new", now=140.0) == 0.0
    assert cd.check_and_consume(1, 30, "ticket:new", now=150.0) == 0.0


def test_uk_dst_slots_and_parsing() -> None:
    # Spring-forward day in UK: 2026-03-29 skips 01:00 -> 02:00 BST.
    before_spring = datetime(2026, 3, 29, 0, 15, tzinfo=UK).timestamp()
    cow_ts, cow_label = next_cow_slot(before_spring)
    assert cow_label == "04:00 UK"
    assert datetime.fromtimestamp(cow_ts, UK).hour == 4

    plant_ts, plant_label = next_plant_slot(before_spring)
    assert plant_label == "00:30 UK"
    next_after_0030, next_plant_label = next_plant_slot(plant_ts)
    assert next_plant_label == "02:30 UK"
    assert next_after_0030 - plant_ts == 3600

    # Fall-back day in UK: 2026-10-25 repeats 01:00 (fold=0 +0100, fold=1 +0000).
    fold0 = datetime(2026, 10, 25, 1, 5, tzinfo=UK, fold=0).timestamp()
    fold1 = datetime(2026, 10, 25, 1, 5, tzinfo=UK, fold=1).timestamp()
    due0 = latest_due_cow_slot(fold0, grace_seconds=900)
    due1 = latest_due_cow_slot(fold1, grace_seconds=900)
    assert due0 is not None and due1 is not None
    assert due0[1] != due1[1]
    assert slot_label_from_key(due0[1]) == "01:00"
    assert slot_label_from_key("2026-10-25-01:30") == "01:30"

    plant_due = latest_due_plant_slot(datetime(2026, 10, 25, 1, 35, tzinfo=UK, fold=1).timestamp(), 900)
    assert plant_due is not None
    assert plant_due[2] == "01:30"

    assert "UK" in uk_str(before_spring) or "GMT" in uk_str(before_spring)
    assert uk_today(before_spring) == "2026-03-29"
    assert uk_day_start_ts(before_spring) < int(before_spring)

    parsed_hhmm = parse_uk_hhmm("18:30", now_ts=before_spring)
    assert datetime.fromtimestamp(parsed_hhmm, UK).hour == 18
    assert parse_uk_event_datetime("25/12/2026", "20:30") > int(before_spring)
    with pytest.raises(ValueError):
        parse_uk_hhmm("25:99")
    with pytest.raises(ValueError):
        parse_uk_event_datetime("29/03/2026", "01:30")
