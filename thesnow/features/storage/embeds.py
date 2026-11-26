import discord

from thesnow.core.embeds import stamp_embed
from thesnow.shared.constants import BLUE, MAX_EMBED_FIELD_CHARS
from thesnow.shared.time import uk_str
from thesnow.shared.validation import clip, is_allowed_discord_image_url

from .service import StorageItem


def build_storage_panel_embed(items: list[StorageItem], guild: discord.Guild | None = None) -> discord.Embed:
    """Build the persistent Shared Storage panel embed."""
    lines: list[str] = []
    for entry in items:
        loc = f" · 📍 `{entry.location}`" if entry.location else ""
        lines.append(f"▪️ **{entry.item}** — `{entry.qty:,}` pcs{loc}")

    embed = discord.Embed(
        title="📦  S H A R E D   S T O R A G E  📦",
        color=BLUE,
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ *Choose **Warehouse** or **Vehicle** (last 3 plate digits) "
            "and attach a screenshot when storing or taking items.*\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ),
    )
    embed.add_field(
        name="📋 Current Inventory",
        value=clip(lines, limit=25, max_chars=MAX_EMBED_FIELD_CHARS) if lines else "Storage is currently empty.",
        inline=False,
    )
    return stamp_embed(embed, guild)


def build_storage_lookup_embed(item: StorageItem) -> discord.Embed:
    """Build the ephemeral Find Item lookup embed."""
    embed = discord.Embed(title=f"🔍 Item Lookup – {item.item}", color=BLUE)
    embed.add_field(name="📦 Current Stock", value=f"**{item.qty:,} pcs**")
    embed.add_field(name="📍 Location", value=item.location or "Unknown")
    embed.add_field(
        name="👤 Last Interacted By",
        value=f"**{item.last_who or 'Unknown'}** ({item.last_action or '—'})",
        inline=False,
    )
    if item.last_ts is not None:
        embed.add_field(
            name="🕒 When",
            value=f"{uk_str(item.last_ts)} (<t:{item.last_ts}:R>)",
            inline=False,
        )
    if is_allowed_discord_image_url(item.last_img):
        embed.set_image(url=item.last_img)
    else:
        embed.set_footer(text="No screenshot logged for this item yet.")
    return embed
