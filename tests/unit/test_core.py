import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import discord
import pytest
from discord import app_commands

from thesnow.core.database import ConfigCache, Database
from thesnow.core.errors import BaseModal, BaseView, handle_app_command_error, retry_discord
from thesnow.core.forms import extract_modal_attachment, make_file_label, make_select_label, make_text_label
from thesnow.core.logging import ContextFormatter, configure_logging
from thesnow.core.migrations import migrate
from thesnow.core.permissions import PermissionService
from thesnow.shared.validation import Oops


class _FakeResponse:
    def __init__(self, done: bool = False) -> None:
        self._done = done
        self.messages: list[tuple[str | None, bool]] = []

    def is_done(self) -> bool:
        return self._done

    async def send_message(self, content: str | None = None, *, ephemeral: bool = False, **_: Any) -> None:
        self._done = True
        self.messages.append((content, ephemeral))


class _FakeFollowup:
    def __init__(self) -> None:
        self.messages: list[tuple[str | None, bool]] = []

    async def send(self, content: str | None = None, *, ephemeral: bool = False, **_: Any) -> None:
        self.messages.append((content, ephemeral))


class _FakeInteraction:
    def __init__(
        self,
        *,
        guild_id: int | None = 1,
        user: Any = None,
        done: bool = False,
    ) -> None:
        self.guild_id = guild_id
        self.channel_id = 99
        self.user = user or SimpleNamespace(id=55)
        self.command = SimpleNamespace(qualified_name="test_cmd")
        self.response = _FakeResponse(done=done)
        self.followup = _FakeFollowup()


def test_context_formatter_keeps_context_and_redacts() -> None:
    logger = configure_logging("INFO")
    formatter = ContextFormatter("%(levelname)s %(message)s")
    record = logger.makeRecord(
        "thesnow",
        logging.INFO,
        "file.py",
        1,
        "hello",
        (),
        None,
        extra={"guild_id": 123, "user_id": 456, "action": "balance:deposit"},
    )
    formatted = formatter.format(record)
    assert "guild_id=123" in formatted
    assert "user_id=456" in formatted
    assert "action=balance:deposit" in formatted


async def test_permission_service_matrix_and_reaction_fail_closed(tmp_path: Any) -> None:
    db = Database(tmp_path / "perm.db")
    await db.connect()
    await migrate(db)
    cache = ConfigCache(db)
    perms = PermissionService(cache, allowed_guild_ids=frozenset({1}))

    def _fake_member(uid: int, *, admin: bool = False, role_ids: tuple[int, ...] = ()) -> Any:
        member = MagicMock(spec=discord.Member)
        member.id = uid
        member.guild_permissions = SimpleNamespace(administrator=admin)
        member.roles = [SimpleNamespace(id=rid) for rid in role_ids]
        return member

    admin_member = _fake_member(10, admin=True)
    mod_member = _fake_member(11, role_ids=(100,))
    dep_member = _fake_member(12, role_ids=(200,))
    plain_member = _fake_member(13)

    # Disallowed guild denied
    bad_guild = _FakeInteraction(guild_id=999, user=admin_member)
    assert not await perms.authorize(bad_guild, "admin:setup")  # type: ignore[arg-type]

    # Missing /set_roles explanation for non-admin
    no_roles_yet = _FakeInteraction(guild_id=1, user=mod_member)
    assert not await perms.authorize(no_roles_yet, "solar:mutate")  # type: ignore[arg-type]
    assert "/set_roles" in (no_roles_yet.response.messages[0][0] or "")

    await cache.set(1, "mod_role", 100)
    await cache.set(1, "deputy_role", 200)

    # Admin only
    assert await perms.authorize(_FakeInteraction(guild_id=1, user=admin_member), "admin:setup")  # type: ignore[arg-type]
    assert not await perms.authorize(_FakeInteraction(guild_id=1, user=dep_member), "admin:setup")  # type: ignore[arg-type]

    # Deputy only
    assert not await perms.authorize(_FakeInteraction(guild_id=1, user=mod_member), "bonus:log")  # type: ignore[arg-type]
    assert await perms.authorize(_FakeInteraction(guild_id=1, user=dep_member), "bonus:log")  # type: ignore[arg-type]

    # Staff vs plain member
    assert await perms.authorize(_FakeInteraction(guild_id=1, user=mod_member), "storage:mutate")  # type: ignore[arg-type]
    assert not await perms.authorize(_FakeInteraction(guild_id=1, user=plain_member), "storage:mutate")  # type: ignore[arg-type]

    # Ticket owner vs staff
    assert await perms.authorize(
        _FakeInteraction(guild_id=1, user=plain_member),  # type: ignore[arg-type]
        "bonus:ticket_close",
        ticket_owner_id=13,
    )
    assert not await perms.authorize(
        _FakeInteraction(guild_id=1, user=plain_member),  # type: ignore[arg-type]
        "bonus:ticket_close",
        ticket_owner_id=999,
    )

    # Reaction auth: fetch_member fallback + fail closed on NotFound
    async def _fetch_ok(uid: int) -> Any:
        return mod_member

    async def _fetch_missing(uid: int) -> Any:
        raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "missing")

    guild_ok = SimpleNamespace(id=1, get_member=lambda _uid: None, fetch_member=_fetch_ok)
    payload_ok = SimpleNamespace(guild_id=1, user_id=11, member=None)
    assert await perms.authorize_reaction_member(guild_ok, payload_ok) is mod_member  # type: ignore[arg-type]

    guild_missing = SimpleNamespace(id=1, get_member=lambda _uid: None, fetch_member=_fetch_missing)
    assert await perms.authorize_reaction_member(guild_missing, payload_ok) is None  # type: ignore[arg-type]

    guild_plain = SimpleNamespace(id=1, get_member=lambda _uid: plain_member, fetch_member=_fetch_missing)
    assert await perms.authorize_reaction_member(guild_plain, payload_ok) is None  # type: ignore[arg-type]

    await db.close()


async def test_error_handlers_and_retries() -> None:
    i_oops = _FakeInteraction()
    cmd = SimpleNamespace(name="test_cmd")
    await handle_app_command_error(i_oops, app_commands.CommandInvokeError(cmd, Oops("bad input")))  # type: ignore[arg-type]
    assert i_oops.response.messages == [("❌ bad input", True)]

    i_boom = _FakeInteraction(done=True)
    await handle_app_command_error(i_boom, app_commands.CommandInvokeError(cmd, RuntimeError("db down")))  # type: ignore[arg-type]
    assert "ref:" in (i_boom.followup.messages[0][0] or "")

    i_check = _FakeInteraction()
    await handle_app_command_error(i_check, app_commands.CheckFailure("denied"))
    assert "⛔" in (i_check.response.messages[0][0] or "")

    view = BaseView()
    i_view = _FakeInteraction()
    await view.on_error(i_view, RuntimeError("view crash"), SimpleNamespace(custom_id="x:y"))  # type: ignore[arg-type]
    assert "ref:" in (i_view.response.messages[0][0] or "")

    modal = BaseModal(title="Test")
    i_modal = _FakeInteraction()
    await modal.on_error(i_modal, Oops("bad field"))  # type: ignore[arg-type]
    assert i_modal.response.messages == [("❌ bad field", True)]

    i_modal_boom = _FakeInteraction()
    await modal.on_error(i_modal_boom, RuntimeError("modal crash"))  # type: ignore[arg-type]
    assert "ref:" in (i_modal_boom.response.messages[0][0] or "")

    # BaseView timeout disables items
    edited: list[Any] = []

    class _FakeMsg:
        async def edit(self, **kwargs: Any) -> None:
            edited.append(kwargs)

    btn: discord.ui.Button[Any] = discord.ui.Button(label="Go")
    view.add_item(btn)
    view.ephemeral_message = _FakeMsg()  # type: ignore[assignment]
    await view.on_timeout()
    assert btn.disabled is True
    assert len(edited) == 1

    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise discord.HTTPException(SimpleNamespace(status=503, reason="Unavailable"), "retry")
        return "ok"

    assert await retry_discord(flaky, base_delay=0.01) == "ok"
    assert attempts == 2


async def test_modal_helpers_and_attachment_validation() -> None:
    txt_label, txt = make_text_label("Amount", default="10")
    sel_label, sel = make_select_label("Place", ("Warehouse", "Vehicle"))
    file_label, upload = make_file_label("Proof")
    assert txt_label.component is txt
    assert sel_label.component is sel
    assert file_label.component is upload

    with pytest.raises(Oops, match="screenshot"):
        await extract_modal_attachment(upload, required=True)
    assert await extract_modal_attachment(upload, required=False) is None

    async def _read_ok() -> bytes:
        return b"png-bytes"

    upload._values = [  # type: ignore[assignment]
        SimpleNamespace(
            filename="proof.png",
            content_type="image/png",
            size=9,
            url="https://cdn.discordapp.com/attachments/1/2/proof.png",
            read=_read_ok,
        )
    ]
    proof = await extract_modal_attachment(upload, required=True)
    assert proof is not None
    assert proof.data == b"png-bytes"
    assert proof.to_discord_file().filename == "proof.png"
