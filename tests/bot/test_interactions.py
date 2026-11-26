import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import discord
import pytest

from thesnow.config import Settings
from thesnow.core.context import AppContext
from thesnow.core.database import ConfigCache, Database
from thesnow.core.migrations import migrate
from thesnow.core.panels import PanelRegistry
from thesnow.core.permissions import PermissionService
from thesnow.core.scheduler import DeadlineScheduler
from thesnow.features import armory, balance, bonus, events, finance, reminders, schedule, seeds, solar, storage
from thesnow.features.armory.service import get_armory_rows, mutate_armory
from thesnow.features.armory.views import ArmoryModal, ArmoryView
from thesnow.features.balance.service import deposit, get_balance_total
from thesnow.features.balance.views import DepositModal, WithdrawModal
from thesnow.features.bonus.views import BonusLogModal, BonusLogView, CloseView, TicketModal, TicketView
from thesnow.features.events.service import create_event, process_due_events
from thesnow.features.finance.service import get_active_loans
from thesnow.features.finance.views import FinanceView, LoanCreateModal, LoanPayModal
from thesnow.features.reminders.service import add_reminder, process_due_reminders
from thesnow.features.schedule.embeds import build_schedule_panel_embed
from thesnow.features.schedule.service import get_active_alert, process_uk_schedules
from thesnow.features.schedule.views import AlertAckView, handle_schedule_reaction
from thesnow.features.seeds.service import get_seed_stock
from thesnow.features.seeds.views import SeedActionView, SeedModal, SeedsView
from thesnow.features.solar.service import get_solar_stock
from thesnow.features.solar.views import SolarAddModal, SolarSellModal, SolarUseModal, SolarView
from thesnow.features.storage.service import find_storage_item
from thesnow.features.storage.views import StorageFindModal, StorageModal, StorageView
from thesnow.main import build_bot, compute_next_deadline
from thesnow.shared.constants import SEEDS
from thesnow.shared.time import UK
from thesnow.shared.validation import Oops


class FakePartialMessage:
    def __init__(self, channel: "FakeTextChannel", msg_id: int) -> None:
        self.channel = channel
        self.id = msg_id

    async def edit(self, **kwargs: Any) -> None:
        if self.channel.edit_error is not None:
            raise self.channel.edit_error
        self.channel.edits.append((self.id, kwargs))

    async def delete(self) -> None:
        self.channel.deletes.append(self.id)


class FakeMessage:
    def __init__(self, msg_id: int, channel: "FakeTextChannel", attachments: list[Any] | None = None) -> None:
        self.id = msg_id
        self.channel = channel
        self.attachments = attachments or []
        self.reactions: list[str] = []

    async def add_reaction(self, emoji: str) -> None:
        self.reactions.append(emoji)


class FakeTextChannel:
    __class__ = discord.TextChannel  # type: ignore[assignment]

    def __init__(self, channel_id: int, name: str = "general", topic: str | None = None) -> None:
        self.id = channel_id
        self.name = name
        self.mention = f"<#{channel_id}>"
        self.topic = topic
        self.category = None
        self.sent: list[dict[str, Any]] = []
        self.edits: list[tuple[int, dict[str, Any]]] = []
        self.deletes: list[int] = []
        self.deleted_channel = False
        self.send_error: Exception | None = None
        self.edit_error: Exception | None = None
        self._next_msg_id = 5000

    def get_partial_message(self, msg_id: int) -> FakePartialMessage:
        return FakePartialMessage(self, msg_id)

    async def send(self, content: str | None = None, **kwargs: Any) -> FakeMessage:
        if self.send_error is not None:
            raise self.send_error
        self._next_msg_id += 1
        atts: list[Any] = []
        if kwargs.get("file") is not None:
            atts.append(SimpleNamespace(url=f"https://cdn.discordapp.com/attachments/1/{self._next_msg_id}/proof.png"))
        msg = FakeMessage(self._next_msg_id, self, attachments=atts)
        self.sent.append({"id": msg.id, "content": content, **kwargs})
        return msg

    async def delete(self) -> None:
        self.deleted_channel = True


class FakeGuild:
    def __init__(self, guild_id: int, channels: dict[int, FakeTextChannel]) -> None:
        self.id = guild_id
        self.icon = None
        self.default_role = MagicMock(spec=discord.Role, id=guild_id)
        self.me = _make_member(999)
        self._channels = channels
        self._members: dict[int, Any] = {}
        self.left = False

    @property
    def text_channels(self) -> list[FakeTextChannel]:
        return list(self._channels.values())

    def get_channel(self, channel_id: int) -> FakeTextChannel | None:
        return self._channels.get(channel_id)

    def get_role(self, role_id: int) -> Any:
        role = MagicMock(spec=discord.Role)
        role.id = role_id
        role.mention = f"<@&{role_id}>"
        return role

    def get_member(self, user_id: int) -> Any:
        return self._members.get(user_id)

    async def fetch_member(self, user_id: int) -> Any:
        member = self._members.get(user_id)
        if member is None:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "unknown")
        return member

    async def create_text_channel(self, name: str, **kwargs: Any) -> FakeTextChannel:
        ch = FakeTextChannel(9001, name=name, topic=kwargs.get("topic"))
        self._channels[ch.id] = ch
        return ch

    async def leave(self) -> None:
        self.left = True


class FakeResponse:
    def __init__(self) -> None:
        self.done = False
        self.messages: list[dict[str, Any]] = []
        self.modals: list[discord.ui.Modal] = []

    def is_done(self) -> bool:
        return self.done

    async def defer(self, *, ephemeral: bool = False) -> None:
        self.done = True
        self.messages.append({"deferred": True, "ephemeral": ephemeral})

    async def send_message(self, content: str | None = None, **kwargs: Any) -> None:
        self.done = True
        self.messages.append({"content": content, **kwargs})

    async def send_modal(self, modal: discord.ui.Modal) -> None:
        self.done = True
        self.modals.append(modal)


class FakeFollowup:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def send(self, content: str | None = None, **kwargs: Any) -> None:
        self.messages.append({"content": content, **kwargs})


class FakeInteraction:
    def __init__(
        self,
        *,
        guild: FakeGuild,
        user: Any,
        channel: FakeTextChannel | None = None,
        message: Any = None,
    ) -> None:
        self.guild = guild
        self.guild_id = guild.id
        self.user = user
        self.channel = channel or guild.text_channels[0]
        self.channel_id = self.channel.id
        self.message = message
        self.response = FakeResponse()
        self.followup = FakeFollowup()

    async def original_response(self) -> Any:
        return SimpleNamespace(edit=lambda **_: asyncio.sleep(0))


def _make_member(user_id: int, *, admin: bool = False, role_ids: tuple[int, ...] = ()) -> Any:
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.name = f"user{user_id}"
    member.display_name = f"User {user_id}"
    member.mention = f"<@{user_id}>"
    member.display_avatar = SimpleNamespace(url="https://cdn.discordapp.com/embed/avatars/0.png")
    member.guild_permissions = SimpleNamespace(administrator=admin)
    member.roles = [SimpleNamespace(id=rid) for rid in role_ids]
    return member


async def _make_ctx(
    tmp_path: Path,
    allowed_guilds: frozenset[int] = frozenset({1}),
) -> tuple[AppContext, FakeGuild, Any]:
    settings = Settings(
        discord_token="tok",
        guild_id=None,
        allowed_guild_ids=allowed_guilds,
        db_path=tmp_path / "bot.db",
    )
    db = Database(settings.db_path)
    await db.connect()
    await migrate(db)
    config = ConfigCache(db)
    await config.set(1, "mod_role", 100)
    await config.set(1, "deputy_role", 200)

    perms = PermissionService(config, settings.allowed_guild_ids)
    panels = PanelRegistry(config)
    scheduler = DeadlineScheduler(lambda _ts: asyncio.sleep(0, result=None))
    ctx = AppContext(
        settings=settings,
        db=db,
        config=config,
        permissions=perms,
        panels=panels,
        scheduler=scheduler,
    )

    ch_panel = FakeTextChannel(10, "panels")
    ch_log = FakeTextChannel(20, "logs")
    guild = FakeGuild(1, {10: ch_panel, 20: ch_log})
    bot = SimpleNamespace(
        user=SimpleNamespace(id=999),
        get_guild=lambda gid: guild if gid == 1 else None,
        get_channel=guild.get_channel,
        add_view=lambda _v: None,
    )
    tree = SimpleNamespace(command=lambda **_: (lambda fn: fn), add_command=lambda _g: None)

    for mod in (balance, seeds, solar, armory, storage, finance, bonus, schedule, reminders, events):
        mod.setup(bot, tree, ctx)  # type: ignore[arg-type]

    return ctx, guild, bot


def test_import_main_has_no_db_side_effects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    import thesnow.main as main_mod

    assert not (tmp_path / "family.db").exists()
    settings = Settings(discord_token="tok", guild_id=None, allowed_guild_ids=frozenset({1}), db_path=tmp_path / "x.db")
    bot = main_mod.build_bot(settings)
    assert bot.settings.guild_id is None


async def test_persistent_custom_ids_and_non_destructive_setup(tmp_path: Path) -> None:
    ctx, guild, _ = await _make_ctx(tmp_path)
    views = ctx.panels.persistent_views() + [CloseView(ctx), AlertAckView(ctx)]
    custom_ids = {
        getattr(item, "custom_id", None)
        for view in views
        for item in view.children
    }
    expected = {
        "bal:cow", "bal:plant", "bal:add", "bal:wd", "bal:check", "bal:hist",
        *(f"seed_pick:{s}" for s in SEEDS),
        "solar:add", "solar:use", "solar:sell", "solar:rep",
        "arm:add", "arm:use",
        "sto:add", "sto:use", "sto:find",
        "fin:taken", "fin:given", "fin:pay",
        "ticket:close", "ticket:new", "bonus:log", "alert:ack",
    }
    assert expected.issubset(custom_ids)

    # Seed armory and add stock, then re-run setup_panel("armory") — stock must NOT be zeroed!
    await mutate_armory(ctx.db, 1, weapon="Gun", mode="add", weapon_qty=5, ammo_qty=100, vest_qty=2)
    await ctx.panels.setup_panel(guild, "armory", guild.get_channel(10), guild.get_channel(20))  # type: ignore[arg-type]
    rows = {r.weapon: r for r in await get_armory_rows(ctx.db, 1)}
    assert rows["Gun"].qty == 5
    assert rows["Gun"].ammo == 100
    assert rows["Vest"].qty == 2

    await ctx.db.close()


async def test_panel_permissions_modals_and_storage_proof_flow(tmp_path: Path) -> None:
    ctx, guild, _ = await _make_ctx(tmp_path)
    panel_ch = guild.get_channel(10)
    log_ch = guild.get_channel(20)
    assert panel_ch is not None and log_ch is not None
    await ctx.panels.setup_panel(guild, "balance", panel_ch, log_ch)  # type: ignore[arg-type]
    await ctx.panels.setup_panel(guild, "solar", panel_ch, log_ch)  # type: ignore[arg-type]
    await ctx.panels.setup_panel(guild, "storage", panel_ch, log_ch)  # type: ignore[arg-type]
    await ctx.panels.setup_panel(guild, "seeds", panel_ch, log_ch)  # type: ignore[arg-type]

    plain = _make_member(50)
    mod = _make_member(51, role_ids=(100,))
    dep = _make_member(52, role_ids=(200,))

    # Plain member blocked from Solar, Armory, Storage mutate, Finance, BonusLog
    for view, method in (
        (SolarView(ctx), "add"),
        (SolarView(ctx), "repaired"),
        (ArmoryView(ctx), "add"),
        (StorageView(ctx), "add"),
        (FinanceView(ctx), "taken"),
        (BonusLogView(ctx), "log"),
    ):
        inter = FakeInteraction(guild=guild, user=plain)
        await getattr(view, method).callback(inter)  # type: ignore[arg-type]
        assert "⛔" in (inter.response.messages[0]["content"] or "")

    # Mod blocked from deputy-only BonusLog
    i_mod_bonus = FakeInteraction(guild=guild, user=mod)
    await BonusLogView(ctx).log.callback(i_mod_bonus)  # type: ignore[arg-type]
    assert "Deputy" in (i_mod_bonus.response.messages[0]["content"] or "")
    i_dep_bonus = FakeInteraction(guild=guild, user=dep)
    await BonusLogView(ctx).log.callback(i_dep_bonus)  # type: ignore[arg-type]
    assert len(i_dep_bonus.response.modals) == 1

    # SolarView.repaired sends ephemeral confirmation after defer
    i_rep = FakeInteraction(guild=guild, user=mod)
    await SolarView(ctx).repaired.callback(i_rep)  # type: ignore[arg-type]
    assert i_rep.response.messages[0]["deferred"] is True
    assert "Solar repair logged" in (i_rep.followup.messages[0]["content"] or "")

    # Balance modal submit updates DB & edits panel in-place (no delete+resend)
    dep_modal = DepositModal(ctx, "Cow Shed")
    dep_modal.amount_input._value = "1500"
    i_dep_sub = FakeInteraction(guild=guild, user=mod)
    await dep_modal.on_submit(i_dep_sub)  # type: ignore[arg-type]
    assert await get_balance_total(ctx.db, 1) == 1500
    assert len(panel_ch.edits) == 2
    assert len(panel_ch.deletes) == 0

    # Concurrent panel refreshes coalesce without raising
    await asyncio.gather(
        ctx.panels.refresh(guild, "balance"),  # type: ignore[arg-type]
        ctx.panels.refresh(guild, "balance"),  # type: ignore[arg-type]
    )

    # Seeds modal with tuple LOCATIONS Select
    seed_view = SeedsView(ctx)
    seed_btn = seed_view.children[0]
    i_seed = FakeInteraction(guild=guild, user=mod)
    await seed_btn.callback(i_seed)  # type: ignore[arg-type]
    action_view = SeedActionView(ctx, "Mandarins")
    i_seed_add = FakeInteraction(guild=guild, user=mod)
    await action_view.add_btn.callback(i_seed_add)  # type: ignore[arg-type]
    seed_modal = i_seed_add.response.modals[0]
    assert isinstance(seed_modal, SeedModal)
    seed_modal.loc_select._values = ["Plantation"]
    seed_modal.qty_input._value = "25"
    await seed_modal.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]
    assert (await get_seed_stock(ctx.db, 1))["Mandarins"] == 25

    # Armory modal with weapon Select
    arm_modal = ArmoryModal(ctx, "add")
    arm_modal.weapon_select._values = ["Gun"]
    arm_modal.w_qty_input._value = "3"
    await arm_modal.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]
    assert next(r for r in await get_armory_rows(ctx.db, 1) if r.weapon == "Gun").qty == 3

    # Storage modal with FileUpload proof re-uploads to log_channel & stores durable log attachment URL
    sto_modal = StorageModal(ctx, "add", "Vehicle")
    assert sto_modal.plate_input is not None
    sto_modal.plate_input._value = "482"
    sto_modal.item_input._value = "medkit"
    sto_modal.qty_input._value = "7"

    async def _read_png() -> bytes:
        return b"imgdata"

    sto_modal.proof_upload._values = [  # type: ignore[assignment]
        SimpleNamespace(
            filename="screen.png",
            content_type="image/png",
            size=7,
            url="https://cdn.discordapp.com/ephemeral/temp.png",
            read=_read_png,
        )
    ]
    await sto_modal.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]
    found = await find_storage_item(ctx.db, 1, "Medkit")
    assert found.qty == 7
    assert found.location == "Vehicle (482)"
    assert found.last_img.startswith("https://cdn.discordapp.com/attachments/1/")

    # Storage Find modal replies ephemerally
    find_modal = StorageFindModal(ctx)
    find_modal.query_input._value = "medkit"
    i_find = FakeInteraction(guild=guild, user=plain)
    await find_modal.on_submit(i_find)  # type: ignore[arg-type]
    assert i_find.response.messages[0]["ephemeral"] is True
    assert i_find.response.messages[0]["embed"].image.url == found.last_img

    await ctx.db.close()


async def test_ticket_flow_panel_notfound_fallback_and_scheduler_isolation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fast_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("thesnow.features.bonus.views.asyncio.sleep", _fast_sleep)
    ctx, guild, bot = await _make_ctx(tmp_path)
    panel_ch = guild.get_channel(10)
    log_ch = guild.get_channel(20)
    assert panel_ch is not None and log_ch is not None

    # Ticket open by plain member + cooldown + close double-click guard
    plain = _make_member(60)
    i_open = FakeInteraction(guild=guild, user=plain, channel=panel_ch)
    await TicketView(ctx).new.callback(i_open)  # type: ignore[arg-type]
    assert len(i_open.response.modals) == 1

    t_modal = TicketModal(ctx)
    t_modal.amount_input._value = "5000"
    t_modal.reason_input._value = "Helped clan"
    i_sub = FakeInteraction(guild=guild, user=plain, channel=panel_ch)
    await t_modal.on_submit(i_sub)  # type: ignore[arg-type]
    assert i_sub.followup.messages[0]["ephemeral"] is True
    ticket_ch = next(c for c in guild.text_channels if c.topic == "bonus_ticket:60")

    close_view = CloseView(ctx)
    i_close1 = FakeInteraction(guild=guild, user=plain, channel=ticket_ch)
    await close_view.close.callback(i_close1)  # type: ignore[arg-type]
    assert ticket_ch.deleted_channel is True

    # Panel edit: transient 503 does NOT create duplicate panel; 404 NotFound DOES re-send
    await ctx.panels.setup_panel(guild, "solar", panel_ch, log_ch)  # type: ignore[arg-type]
    sent_before = len(panel_ch.sent)
    panel_ch.edit_error = discord.HTTPException(SimpleNamespace(status=503, reason="Service Unavailable"), "503")
    await ctx.panels.refresh(guild, "solar")
    assert len(panel_ch.sent) == sent_before

    panel_ch.edit_error = discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "missing")
    await ctx.panels.refresh(guild, "solar")
    assert len(panel_ch.sent) == sent_before + 1

    # UK Schedule slot trigger + fail-closed reaction auth + button ack
    await ctx.config.set(1, "plantation_rem_enabled", "1")
    await ctx.config.set(1, "plantation_rem_role", "100")
    await ctx.config.set(1, "plantation_rem_ch", "10")
    await ctx.config.set(1, "cowshed_rem_ch", "10")

    slot_ts = int(datetime(2026, 11, 27, 12, 32, tzinfo=UK).timestamp())
    await process_uk_schedules(ctx, bot, slot_ts, ack_view_factory=lambda: AlertAckView(ctx))
    alert = await get_active_alert(ctx, 1, "plantation")
    assert alert is not None and alert.ack == 0

    # Wrong emoji ignored; uncached plain user rejected fail-closed; mod fetch_member succeeds
    guild._members[70] = _make_member(70)
    guild._members[71] = _make_member(71, role_ids=(100,))
    await handle_schedule_reaction(
        ctx,
        bot,
        SimpleNamespace(guild_id=1, user_id=71, message_id=alert.msg_id, emoji="❌", member=None),  # type: ignore[arg-type]
    )
    assert (await get_active_alert(ctx, 1, "plantation")).ack == 0  # type: ignore[union-attr]

    await handle_schedule_reaction(
        ctx,
        bot,
        SimpleNamespace(guild_id=1, user_id=70, message_id=alert.msg_id, emoji="✅", member=None),  # type: ignore[arg-type]
    )
    assert (await get_active_alert(ctx, 1, "plantation")).ack == 0  # type: ignore[union-attr]

    await handle_schedule_reaction(
        ctx,
        bot,
        SimpleNamespace(guild_id=1, user_id=71, message_id=alert.msg_id, emoji="✅", member=None),  # type: ignore[arg-type]
    )
    assert (await get_active_alert(ctx, 1, "plantation")).ack == 1  # type: ignore[union-attr]

    # Button ack works for staff member on cowshed alert
    cow_slot_ts = int(datetime(2026, 11, 27, 13, 1, tzinfo=UK).timestamp())
    await process_uk_schedules(ctx, bot, cow_slot_ts, ack_view_factory=lambda: AlertAckView(ctx))
    cow_alert = await get_active_alert(ctx, 1, "cowshed")
    assert cow_alert is not None and cow_alert.ack == 0
    i_ack = FakeInteraction(
        guild=guild,
        user=guild._members[71],
        channel=panel_ch,
        message=SimpleNamespace(id=cow_alert.msg_id),
    )
    await AlertAckView(ctx).mark_done.callback(i_ack)  # type: ignore[arg-type]
    assert (await get_active_alert(ctx, 1, "cowshed")).ack == 1  # type: ignore[union-attr]

    # Reminders & Events fault isolation: dead/forbidden channel 10 doesn't stop healthy channel 20
    panel_ch.send_error = discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "no perm")
    await add_reminder(
        ctx.db, 1, chapter="Bad", channel_id=10, role_id=100, message="x", interval_min=60, next_run=100
    )
    await add_reminder(
        ctx.db, 1, chapter="Good", channel_id=20, role_id=100, message="ok", interval_min=60, next_run=100
    )
    await process_due_reminders(ctx, bot, 200)
    assert any("ok" in (m["content"] or "") for m in log_ch.sent)

    await create_event(
        ctx.db, 1, title="DeadEv", description="", channel_id=10, role_id=100, start_ts=150, remind_min=10
    )
    await create_event(
        ctx.db, 1, title="LiveEv", description="", channel_id=20, role_id=100, start_ts=150, remind_min=10
    )
    await process_due_events(ctx, bot, 200)
    assert any("LiveEv" in (m["content"] or "") for m in log_ch.sent)

    # Guild join allowlist enforcement
    app_bot = build_bot(ctx.settings)
    bad_guild = FakeGuild(999, {})
    await app_bot.on_guild_join(bad_guild)  # type: ignore[arg-type]
    assert bad_guild.left is True

    await ctx.db.close()


async def test_balance_withdraw_and_insufficient_funds_modal(tmp_path: Path) -> None:
    import pytest as _pytest

    ctx, guild, _ = await _make_ctx(tmp_path)
    panel_ch = guild.get_channel(10)
    log_ch = guild.get_channel(20)
    await ctx.panels.setup_panel(guild, "balance", panel_ch, log_ch)  # type: ignore[arg-type]
    mod = _make_member(51, role_ids=(100,))

    await deposit(ctx.db, 1, amount=1000, source="Plantation", who="Mod")
    wd_fail = WithdrawModal(ctx)
    wd_fail.pid_input._value = "12"
    wd_fail.ign_input._value = "ModIGN"
    wd_fail.amount_input._value = "5000"
    wd_fail.reason_input._value = "Too much"
    with _pytest.raises(Oops, match="Not enough money"):
        await wd_fail.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]
    assert await get_balance_total(ctx.db, 1) == 1000

    wd_ok = WithdrawModal(ctx)
    wd_ok.pid_input._value = "12"
    wd_ok.ign_input._value = "ModIGN"
    wd_ok.amount_input._value = "400"
    wd_ok.reason_input._value = "Fuel"
    i_ok = FakeInteraction(guild=guild, user=mod)
    await wd_ok.on_submit(i_ok)  # type: ignore[arg-type]
    assert await get_balance_total(ctx.db, 1) == 600
    assert "Withdrew" in (i_ok.followup.messages[0]["content"] or "")
    await ctx.db.close()


async def test_armory_modal_validation_and_atomic_take(tmp_path: Path) -> None:
    ctx, guild, _ = await _make_ctx(tmp_path)
    panel_ch = guild.get_channel(10)
    log_ch = guild.get_channel(20)
    await ctx.panels.setup_panel(guild, "armory", panel_ch, log_ch)  # type: ignore[arg-type]
    mod = _make_member(51, role_ids=(100,))

    await mutate_armory(ctx.db, 1, weapon="Gun", mode="add", weapon_qty=2, ammo_qty=50, vest_qty=2)

    zero_modal = ArmoryModal(ctx, "use")
    zero_modal.weapon_select._values = ["Gun"]
    assert zero_modal.reason_input is not None
    zero_modal.reason_input._value = "Patrol"
    with pytest.raises(Oops, match="at least 1"):
        await zero_modal.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]

    bad_modal = ArmoryModal(ctx, "use")
    bad_modal.weapon_select._values = ["Gun"]
    bad_modal.w_qty_input._value = "1"
    bad_modal.a_qty_input._value = "999"
    bad_modal.v_qty_input._value = "1"
    assert bad_modal.reason_input is not None
    bad_modal.reason_input._value = "Patrol"
    with pytest.raises(Oops, match="Not enough stock"):
        await bad_modal.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]

    rows = {r.weapon: r for r in await get_armory_rows(ctx.db, 1)}
    assert rows["Vest"].qty == 2

    ok_modal = ArmoryModal(ctx, "use")
    ok_modal.weapon_select._values = ["Gun"]
    ok_modal.w_qty_input._value = "1"
    ok_modal.a_qty_input._value = "20"
    ok_modal.v_qty_input._value = "1"
    assert ok_modal.reason_input is not None
    ok_modal.reason_input._value = "Turf"
    await ok_modal.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]

    rows_after = {r.weapon: r for r in await get_armory_rows(ctx.db, 1)}
    assert rows_after["Gun"].qty == 1
    assert rows_after["Gun"].ammo == 30
    assert rows_after["Vest"].qty == 1
    await ctx.db.close()


async def test_solar_add_use_sell_modals_and_insufficient_stock(tmp_path: Path) -> None:
    ctx, guild, _ = await _make_ctx(tmp_path)
    panel_ch = guild.get_channel(10)
    log_ch = guild.get_channel(20)
    await ctx.panels.setup_panel(guild, "solar", panel_ch, log_ch)  # type: ignore[arg-type]
    mod = _make_member(51, role_ids=(100,))

    add_m = SolarAddModal(ctx)
    add_m.qty_input._value = "10"
    add_m.note_input._value = "Morning batch"
    await add_m.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]
    assert await get_solar_stock(ctx.db, 1) == 10

    use_m = SolarUseModal(ctx)
    use_m.qty_input._value = "4"
    use_m.desc_input._value = "Generator"
    await use_m.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]
    assert await get_solar_stock(ctx.db, 1) == 6

    sell_m = SolarSellModal(ctx)
    sell_m.qty_input._value = "5"
    sell_m.price_input._value = "200"
    await sell_m.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]
    assert await get_solar_stock(ctx.db, 1) == 1

    over_sell = SolarSellModal(ctx)
    over_sell.qty_input._value = "5"
    over_sell.price_input._value = "200"
    with pytest.raises(Oops, match="Only 1 batteries"):
        await over_sell.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]
    await ctx.db.close()


async def test_finance_loan_create_and_pay_modal_with_proof(tmp_path: Path) -> None:
    ctx, guild, _ = await _make_ctx(tmp_path)
    panel_ch = guild.get_channel(10)
    log_ch = guild.get_channel(20)
    await ctx.panels.setup_panel(guild, "finance", panel_ch, log_ch)  # type: ignore[arg-type]
    mod = _make_member(51, role_ids=(100,))

    create_m = LoanCreateModal(ctx, "taken")
    create_m.party_input._value = "Allies"
    create_m.amount_input._value = "10000"
    create_m.note_input._value = "Cars"
    await create_m.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]
    assert len(await get_active_loans(ctx.db, 1)) == 1

    async def _read_img() -> bytes:
        return b"proof-bytes"

    pay_m = LoanPayModal(ctx)
    pay_m.party_input._value = "allies"
    pay_m.amount_input._value = "10000"
    pay_m.proof_upload._values = [  # type: ignore[assignment]
        SimpleNamespace(
            filename="receipt.png",
            content_type="image/png",
            size=11,
            url="https://cdn.discordapp.com/attachments/1/2/receipt.png",
            read=_read_img,
        )
    ]
    await pay_m.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]
    assert await get_active_loans(ctx.db, 1) == []

    bonus_m = BonusLogModal(ctx)
    bonus_m.to_input._value = "Sam"
    bonus_m.amount_input._value = "2500"
    bonus_m.reason_input._value = "Raid"
    dep = _make_member(52, role_ids=(200,))
    await ctx.panels.setup_panel(guild, "bonus_log", panel_ch, log_ch)  # type: ignore[arg-type]
    await bonus_m.on_submit(FakeInteraction(guild=guild, user=dep))  # type: ignore[arg-type]
    await ctx.db.close()


async def test_ticket_cooldown_and_close_double_click_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    gate = asyncio.Event()

    async def _slow_sleep(_seconds: float) -> None:
        started.set()
        await gate.wait()

    monkeypatch.setattr("thesnow.features.bonus.views.asyncio.sleep", _slow_sleep)
    ctx, guild, _ = await _make_ctx(tmp_path)
    panel_ch = guild.get_channel(10)
    plain = _make_member(80)
    stranger = _make_member(81)

    i1 = FakeInteraction(guild=guild, user=plain, channel=panel_ch)
    await TicketView(ctx).new.callback(i1)  # type: ignore[arg-type]
    assert len(i1.response.modals) == 1

    i2 = FakeInteraction(guild=guild, user=plain, channel=panel_ch)
    await TicketView(ctx).new.callback(i2)  # type: ignore[arg-type]
    assert "Please wait" in (i2.response.messages[0]["content"] or "")

    ticket_ch = await guild.create_text_channel("bonus-user80", topic="bonus_ticket:80")
    close_view = CloseView(ctx)

    # Stranger cannot close someone else's ticket
    i_stranger = FakeInteraction(guild=guild, user=stranger, channel=ticket_ch)
    await close_view.close.callback(i_stranger)  # type: ignore[arg-type]
    assert "⛔" in (i_stranger.response.messages[0]["content"] or "")

    # Concurrent double click only runs deletion once
    task1 = asyncio.create_task(
        close_view.close.callback(FakeInteraction(guild=guild, user=plain, channel=ticket_ch))  # type: ignore[arg-type]
    )
    await asyncio.wait_for(started.wait(), timeout=2.0)
    i_dup = FakeInteraction(guild=guild, user=plain, channel=ticket_ch)
    await close_view.close.callback(i_dup)  # type: ignore[arg-type]
    assert "already closing" in (i_dup.response.messages[0]["content"] or "")
    gate.set()
    await task1
    assert ticket_ch.deleted_channel is True
    await ctx.db.close()


async def test_storage_modal_rejects_bad_plate_and_non_image_upload(tmp_path: Path) -> None:
    ctx, guild, _ = await _make_ctx(tmp_path)
    mod = _make_member(51, role_ids=(100,))

    bad_plate_modal = StorageModal(ctx, "add", "Vehicle")
    assert bad_plate_modal.plate_input is not None
    bad_plate_modal.plate_input._value = "12"
    bad_plate_modal.item_input._value = "Steel"
    bad_plate_modal.qty_input._value = "5"
    with pytest.raises(Oops, match="last 3 characters"):
        await bad_plate_modal.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]

    async def _read_txt() -> bytes:
        return b"not-an-image"

    bad_file_modal = StorageModal(ctx, "add", "Warehouse")
    bad_file_modal.item_input._value = "Steel"
    bad_file_modal.qty_input._value = "5"
    bad_file_modal.proof_upload._values = [  # type: ignore[assignment]
        SimpleNamespace(
            filename="readme.txt",
            content_type="text/plain",
            size=12,
            url="https://cdn.discordapp.com/attachments/1/2/readme.txt",
            read=_read_txt,
        )
    ]
    with pytest.raises(Oops, match="valid image file"):
        await bad_file_modal.on_submit(FakeInteraction(guild=guild, user=mod))  # type: ignore[arg-type]

    with pytest.raises(Oops, match="No item matching"):
        await find_storage_item(ctx.db, 1, "Steel")
    await ctx.db.close()


async def test_schedule_panel_clears_due_status_and_bot_clears_cache_on_remove(tmp_path: Path) -> None:
    ctx, guild, _ = await _make_ctx(tmp_path)
    due_embed = build_schedule_panel_embed(
        "cowshed",
        alert=SimpleNamespace(ack=0, slot_key="2026-11-27-13:00+0000"),  # type: ignore[arg-type]
        last_done=None,
        guild=guild,  # type: ignore[arg-type]
        now_ts=1_795_700_000,
    )
    assert "DUE NOW" in (due_embed.description or "")

    cleared_embed = build_schedule_panel_embed(
        "cowshed",
        alert=None,
        last_done="<@71>",
        guild=guild,  # type: ignore[arg-type]
        now_ts=1_795_700_000,
    )
    assert "Next Cow Feed" in (cleared_embed.description or "")

    await add_reminder(
        ctx.db,
        1,
        chapter="Test",
        channel_id=10,
        role_id=100,
        message="hi",
        interval_min=60,
        next_run=500,
    )
    deadline = await compute_next_deadline(ctx, 400)
    assert deadline == 500.0

    app_bot = build_bot(ctx.settings)
    await app_bot.ctx.db.connect()
    await migrate(app_bot.ctx.db)
    await app_bot.ctx.config.set(1, "mod_role", 100)
    assert (1, "mod_role") in app_bot.ctx.config._values
    await app_bot.on_guild_remove(guild)  # type: ignore[arg-type]
    assert (1, "mod_role") not in app_bot.ctx.config._values
    await app_bot.ctx.db.close()
    await ctx.db.close()


async def test_familybot_setup_hook_and_close_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        discord_token="test-token",
        guild_id=1,
        allowed_guild_ids=frozenset({1}),
        db_path=tmp_path / "lifecycle.db",
    )
    app_bot = build_bot(settings)
    synced: list[int | None] = []

    async def _fake_sync(*, guild: discord.abc.Snowflake | None = None) -> list[Any]:
        synced.append(guild.id if guild is not None else None)
        return []

    monkeypatch.setattr(app_bot.tree, "sync", _fake_sync)
    await app_bot.setup_hook()
    assert app_bot.schema_version == 2
    assert synced == [1]
    assert app_bot.ctx.panels.get("balance").key == "balance"
    assert app_bot.ctx.panels.get("armory").key == "armory"
    assert len(app_bot.persistent_views) >= 10
    await app_bot.close()
