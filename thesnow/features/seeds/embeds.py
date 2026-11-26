import discord

from thesnow.core.embeds import stamp_embed
from thesnow.shared.constants import GREEN, SEED_EMOJI, SEEDS
from thesnow.shared.validation import bar


def build_seeds_panel_embed(stock: dict[str, int], guild: discord.Guild | None = None) -> discord.Embed:
    """Build the persistent Seed Inventory embed from a single-query stock map."""
    total = sum(stock.get(seed, 0) for seed in SEEDS)
    embed = discord.Embed(
        title="🌱  S E E D   I N V E N T O R Y  🌱",
        color=GREEN,
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "### 🌾 Total Seeds in Stock\n"
            f"# {total:,} pcs\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "*Click any seed button below to **Add** or **Use** stock.*"
        ),
    )
    for seed in SEEDS:
        qty = stock.get(seed, 0)
        pct = round(100 * qty / total) if total else 0
        embed.add_field(
            name=f"{SEED_EMOJI[seed]} {seed}",
            value=f"**{qty:,} pcs**\n`{bar(qty, total, 8)}` {pct}%",
            inline=True,
        )
    return stamp_embed(embed, guild)
