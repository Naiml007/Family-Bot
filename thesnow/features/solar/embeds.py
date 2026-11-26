import discord

from thesnow.core.embeds import stamp_embed
from thesnow.shared.constants import GOLD, MAX_EMBED_FIELD_CHARS
from thesnow.shared.time import uk_str
from thesnow.shared.validation import clip

from .service import SolarStats


def build_solar_panel_embed(stats: SolarStats, guild: discord.Guild | None = None) -> discord.Embed:
    """Build the persistent Solar Plantation embed."""
    lines: list[str] = []
    for entry in stats.recent:
        if entry.kind == "add":
            lines.append(f"🟢 **+{entry.qty}** Added · {entry.who} · <t:{entry.ts}:R>")
        elif entry.kind == "use":
            lines.append(f"🟠 **-{entry.qty}** Used ({entry.detail}) · {entry.who} · <t:{entry.ts}:R>")
        else:
            sale = entry.qty * entry.price
            lines.append(
                f"💰 **-{entry.qty}** Sold @ ${entry.price:,}/ea (**${sale:,}**) · {entry.who} · <t:{entry.ts}:R>"
            )

    embed = discord.Embed(
        title="☀️  S O L A R   P L A N T A T I O N  ☀️",
        color=GOLD,
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "### 🔋 Batteries In Stock\n"
            f"# {stats.stock:,} pcs\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ),
    )
    embed.add_field(name="➕ Added Today", value=f"**{stats.added_today}**")
    embed.add_field(name="➖ Used Today", value=f"**{stats.used_today}**")
    embed.add_field(name="💰 Sold Today", value=f"**{stats.sold_today}**")
    embed.add_field(name="💵 Total Sales Revenue", value=f"**${stats.total_revenue:,}**")
    embed.add_field(
        name="🔧 Last Solar Repair",
        value=uk_str(stats.last_repair_ts) if stats.last_repair_ts else "Never logged",
        inline=False,
    )
    embed.add_field(
        name="🕘 Recent Battery Activity",
        value=clip(lines, limit=5, max_chars=MAX_EMBED_FIELD_CHARS) if lines else "No activity logged yet",
        inline=False,
    )
    return stamp_embed(embed, guild)
