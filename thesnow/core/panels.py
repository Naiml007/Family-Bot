import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import discord
from discord import app_commands

from .database import ConfigCache
from .errors import retry_discord

logger = logging.getLogger("thesnow.panels")


@dataclass(frozen=True)
class PanelSpec:
    """Definition of a persistent panel registered by a feature module."""

    key: str
    label: str
    build_embed: Callable[[discord.Guild], Awaitable[discord.Embed]]
    build_view: Callable[[], discord.ui.View] | None = None
    on_setup: Callable[[int], Awaitable[None]] | None = None


@dataclass
class _RefreshState:
    lock: asyncio.Lock
    dirty: bool = False
    running: bool = False


class PanelRegistry:
    """Feature panel registry with coalescing single-flight in-place updates."""

    def __init__(self, config: ConfigCache) -> None:
        self.config = config
        self._specs: dict[str, PanelSpec] = {}
        self._states: dict[tuple[int, str], _RefreshState] = {}

    def register(self, spec: PanelSpec) -> None:
        """Register a panel specification under its unique feature key."""
        if spec.key in self._specs:
            raise ValueError(f"Duplicate panel key: {spec.key}")
        self._specs[spec.key] = spec

    def get(self, key: str) -> PanelSpec:
        """Look up a registered panel spec by feature key."""
        return self._specs[key]

    def persistent_views(self) -> list[discord.ui.View]:
        """Instantiate one persistent view per registered interactive panel."""
        return [spec.build_view() for spec in self._specs.values() if spec.build_view is not None]

    def choices(self) -> list[app_commands.Choice[str]]:
        """Build slash-command choices for setup-managed panels."""
        return [
            app_commands.Choice(name=spec.label, value=spec.key)
            for spec in self._specs.values()
            if spec.build_view is not None
        ]

    async def send_log(
        self,
        guild: discord.Guild,
        feature: str,
        embed: discord.Embed,
        *,
        file: discord.File | None = None,
    ) -> discord.Message | None:
        """Send an audit log embed to the configured feature log channel."""
        cid = await self.config.get(guild.id, f"{feature}_log")
        if not cid or not cid.isdigit():
            return None
        channel = guild.get_channel(int(cid))
        if not isinstance(channel, discord.TextChannel):
            return None

        async def _send() -> discord.Message:
            if file is not None:
                return await channel.send(embed=embed, file=file)
            return await channel.send(embed=embed)

        try:
            return await retry_discord(_send)
        except discord.HTTPException:
            logger.exception(
                "Failed to send feature log embed",
                extra={"guild_id": guild.id, "channel_id": channel.id, "feature": feature},
            )
            return None

    async def setup_panel(
        self,
        guild: discord.Guild,
        feature: str,
        panel_channel: discord.TextChannel,
        log_channel: discord.TextChannel | None = None,
    ) -> discord.Message:
        """Post a panel message via /setup and save channel, message, and log IDs."""
        spec = self.get(feature)
        if spec.on_setup is not None:
            await spec.on_setup(guild.id)

        old_cid, old_mid = (
            await self.config.get(guild.id, f"{feature}_channel"),
            await self.config.get(guild.id, f"{feature}_msg"),
        )
        if old_cid and old_mid and old_cid.isdigit() and old_mid.isdigit():
            old_ch = guild.get_channel(int(old_cid))
            if isinstance(old_ch, discord.TextChannel):
                try:
                    await old_ch.get_partial_message(int(old_mid)).delete()
                except discord.HTTPException:
                    pass

        embed = await spec.build_embed(guild)
        kwargs: dict[str, Any] = {"embed": embed}
        if spec.build_view is not None:
            kwargs["view"] = spec.build_view()
        msg = await retry_discord(lambda: panel_channel.send(**kwargs))

        await self.config.set(guild.id, f"{feature}_channel", panel_channel.id)
        await self.config.set(guild.id, f"{feature}_msg", msg.id)
        if log_channel is not None:
            await self.config.set(guild.id, f"{feature}_log", log_channel.id)
        return msg

    async def refresh(
        self,
        guild: discord.Guild,
        feature: str,
        *,
        channel_key: str | None = None,
        msg_key: str | None = None,
    ) -> None:
        """Update a panel message in place, coalescing concurrent refresh requests."""
        key = (guild.id, feature)
        state = self._states.get(key)
        if state is None:
            state = _RefreshState(lock=asyncio.Lock())
            self._states[key] = state
        state.dirty = True
        if state.running:
            return

        ch_cfg_key = channel_key or f"{feature}_channel"
        msg_cfg_key = msg_key or f"{feature}_msg"

        async with state.lock:
            if state.running:
                return
            state.running = True
            try:
                while state.dirty:
                    state.dirty = False
                    await self._refresh_once(guild, feature, ch_cfg_key, msg_cfg_key)
            finally:
                state.running = False

    async def _refresh_once(
        self,
        guild: discord.Guild,
        feature: str,
        channel_key: str,
        msg_key: str,
    ) -> None:
        spec = self.get(feature)
        cfg = await self.config.get_many(guild.id, channel_key, msg_key)
        cid_raw = cfg[channel_key]
        mid_raw = cfg[msg_key]
        if not cid_raw or not cid_raw.isdigit():
            return
        channel = guild.get_channel(int(cid_raw))
        if not isinstance(channel, discord.TextChannel):
            return

        embed = await spec.build_embed(guild)
        edit_kwargs: dict[str, Any] = {"embed": embed}
        if spec.build_view is not None:
            edit_kwargs["view"] = spec.build_view()

        if mid_raw and mid_raw.isdigit():
            partial = channel.get_partial_message(int(mid_raw))
            try:
                await retry_discord(lambda: partial.edit(**edit_kwargs))
                return
            except discord.NotFound:
                pass
            except discord.HTTPException:
                logger.exception(
                    "Panel edit failed without falling back to duplicate send",
                    extra={"guild_id": guild.id, "channel_id": channel.id, "feature": feature},
                )
                return

        try:
            msg = await retry_discord(lambda: channel.send(**edit_kwargs))
            await self.config.set(guild.id, msg_key, msg.id)
        except discord.HTTPException:
            logger.exception(
                "Panel replacement send failed",
                extra={"guild_id": guild.id, "channel_id": channel.id, "feature": feature},
            )
