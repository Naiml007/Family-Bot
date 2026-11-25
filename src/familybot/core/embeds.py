"""Shared embed styling so cogs never hand-roll colors or footers."""

from __future__ import annotations

import discord

from familybot.core.logging import get_correlation_id
from familybot.core.time import utcnow

COLOR_INFO = discord.Color.blurple()
COLOR_SUCCESS = discord.Color.green()
COLOR_WARNING = discord.Color.gold()
COLOR_ERROR = discord.Color.red()


def make_embed(
    *,
    title: str,
    description: str | None = None,
    color: discord.Color = COLOR_INFO,
    footer_extra: str | None = None,
) -> discord.Embed:
    """Create a consistently styled embed with UTC timestamp and correlation ref."""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=utcnow(),
    )
    cid = get_correlation_id()
    footer_parts: list[str] = ["Family Bot"]
    if cid:
        footer_parts.append(f"ref: {cid}")
    if footer_extra:
        footer_parts.append(footer_extra)
    embed.set_footer(text=" • ".join(footer_parts))
    return embed


def info_embed(title: str, description: str | None = None) -> discord.Embed:
    """Return a standard informational embed."""
    return make_embed(title=title, description=description, color=COLOR_INFO)


def success_embed(title: str, description: str | None = None) -> discord.Embed:
    """Return a standard success embed."""
    return make_embed(title=title, description=description, color=COLOR_SUCCESS)


def warning_embed(title: str, description: str | None = None) -> discord.Embed:
    """Return a standard warning embed."""
    return make_embed(title=title, description=description, color=COLOR_WARNING)


def error_embed(title: str, description: str | None = None) -> discord.Embed:
    """Return a standard error embed."""
    return make_embed(title=title, description=description, color=COLOR_ERROR)
