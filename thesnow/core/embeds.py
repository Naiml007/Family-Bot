import time
from collections.abc import Mapping

import discord

from thesnow.shared.time import uk_str
from thesnow.shared.validation import is_allowed_discord_image_url


def stamp_embed(
    embed: discord.Embed,
    guild: discord.Guild | None = None,
    *,
    now_ts: float | None = None,
) -> discord.Embed:
    """Attach the guild thumbnail and current UK timestamp footer to an embed."""
    if guild is not None and guild.icon is not None:
        embed.set_thumbnail(url=guild.icon.url)
    ts = now_ts if now_ts is not None else time.time()
    embed.set_footer(text=f"Last updated {uk_str(ts)} (UK time)")
    return embed


def log_embed(
    title: str,
    color: int,
    user: discord.abc.User,
    fields: Mapping[str, object],
    image_url: str | None = None,
    *,
    now_ts: float | None = None,
) -> discord.Embed:
    """Build an audit log embed with safe image URL enforcement."""
    embed = discord.Embed(title=title, color=color)
    for key, value in fields.items():
        text = str(value) if value is not None else ""
        embed.add_field(name=key, value=text or "—", inline=True)
    embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    if is_allowed_discord_image_url(image_url):
        embed.set_image(url=image_url)
    ts = now_ts if now_ts is not None else time.time()
    embed.set_footer(text=f"{uk_str(ts)} (UK)")
    return embed
