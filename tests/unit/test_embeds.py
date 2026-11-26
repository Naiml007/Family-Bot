
from thesnow.core.embeds import log_embed
from thesnow.features.armory.embeds import build_armory_panel_embed
from thesnow.features.armory.service import ArmoryRow
from thesnow.features.events.embeds import build_events_list_embed
from thesnow.features.events.service import EventRecord
from thesnow.features.finance.embeds import build_finance_panel_embed
from thesnow.features.finance.service import LoanRecord
from thesnow.features.reminders.embeds import build_reminders_list_embed
from thesnow.features.reminders.service import ReminderRecord
from thesnow.features.storage.embeds import build_storage_panel_embed
from thesnow.features.storage.service import StorageItem
from thesnow.shared.constants import BLUE, MAX_EMBED_DESC_CHARS, MAX_EMBED_FIELD_CHARS, MAX_EMBED_FIELDS


class _FakeAvatar:
    url = "https://cdn.discordapp.com/embed/avatars/0.png"


class _FakeUser:
    display_name = "Tester"
    display_avatar = _FakeAvatar()


def test_embeds_respect_discord_limits() -> None:
    armory_rows = [
        ArmoryRow(weapon=f"Very Long Weapon Name Number {i} Extra Text", qty=i, ammo=i * 100)
        for i in range(30)
    ]
    armory_rows.append(ArmoryRow(weapon="Vest", qty=5, ammo=0))
    arm_embed = build_armory_panel_embed(armory_rows)
    assert len(arm_embed.fields[1].value or "") <= MAX_EMBED_FIELD_CHARS

    storage_items = [
        StorageItem(
            item=f"Storage Item Long Name {i} " + ("X" * 40),
            qty=i + 1,
            location="Vehicle (482)",
            last_who="Bob",
            last_action="Stored",
            last_img="",
            last_ts=1_700_000_000,
        )
        for i in range(30)
    ]
    sto_embed = build_storage_panel_embed(storage_items)
    assert len(sto_embed.fields[0].value or "") <= MAX_EMBED_FIELD_CHARS

    loans = [
        LoanRecord(loan_id=i, party=f"Borrower {i} " + ("Y" * 20), direction="taken", total=1000, paid=100, note="")
        for i in range(25)
    ]
    fin_embed = build_finance_panel_embed(loans)
    assert len(fin_embed.fields[2].value or "") <= MAX_EMBED_FIELD_CHARS

    reminders = [
        ReminderRecord(
            reminder_id=i,
            guild_id=1,
            chapter=f"Chapter {i}",
            channel_id=10,
            role_id=20,
            message="hi",
            interval_min=60,
            next_run=1_800_000_000,
        )
        for i in range(35)
    ]
    rem_embed = build_reminders_list_embed(reminders)
    assert len(rem_embed.fields) <= MAX_EMBED_FIELDS

    events = [
        EventRecord(
            event_id=i,
            guild_id=1,
            title=f"Event Title {i} " + ("Z" * 100),
            description="",
            channel_id=10,
            role_id=20,
            start_ts=1_800_000_000,
            remind_min=30,
            remind_sent=0,
            start_sent=0,
        )
        for i in range(60)
    ]
    ev_embed = build_events_list_embed(events)
    assert len(ev_embed.description or "") <= MAX_EMBED_DESC_CHARS


def test_log_embed_filters_untrusted_image_urls() -> None:
    user = _FakeUser()
    unsafe = log_embed("Test", BLUE, user, {"K": "V"}, image_url="https://evil.tracker/pixel.png")  # type: ignore[arg-type]
    assert unsafe.image.url is None

    safe_cdn = log_embed(
        "Test",
        BLUE,
        user,  # type: ignore[arg-type]
        {"K": "V"},
        image_url="https://cdn.discordapp.com/attachments/1/2/ok.png",
    )
    assert safe_cdn.image.url == "https://cdn.discordapp.com/attachments/1/2/ok.png"

    safe_att = log_embed("Test", BLUE, user, {"K": "V"}, image_url="attachment://proof.png")  # type: ignore[arg-type]
    assert safe_att.image.url == "attachment://proof.png"
