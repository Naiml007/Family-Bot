import discord

from thesnow.core.embeds import stamp_embed
from thesnow.shared.constants import BLUE, GREEN, MAX_EMBED_FIELD_CHARS
from thesnow.shared.validation import clip

from .service import BonusStats


def build_ticket_panel_embed(guild: discord.Guild | None = None) -> discord.Embed:
    """Build the persistent Bonus Request ticket panel embed."""
    embed = discord.Embed(
        title="🎟️  B O N U S   R E Q U E S T  🎟️",
        color=BLUE,
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Need a bonus? Press the button below and submit the request form.\n"
            "A **private ticket** opens that only you and leadership can see.\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ),
    )
    return stamp_embed(embed, guild)


def build_bonus_log_panel_embed(stats: BonusStats, guild: discord.Guild | None = None) -> discord.Embed:
    """Build the persistent Bonus Payout Logs panel embed."""
    lines = [
        f"💵 **${entry.amount:,}** → **{entry.paid_to}** ({entry.reason[:30]}) · by {entry.who} · <t:{entry.ts}:R>"
        for entry in stats.recent
    ]
    embed = discord.Embed(
        title="💵  B O N U S   P A Y O U T   L O G S  💵",
        color=GREEN,
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "### 💸 Total Bonuses Paid\n"
            f"# ${stats.total_paid:,}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "**Deputy / Chief only.** Paid someone a bonus? Press the button below to log it."
        ),
    )
    embed.add_field(name="🧾 Total Payouts", value=f"**{stats.payout_count}**")
    embed.add_field(
        name="🕘 Recent Bonus Payouts",
        value=clip(lines, limit=6, max_chars=MAX_EMBED_FIELD_CHARS) if lines else "No bonuses logged yet.",
        inline=False,
    )
    return stamp_embed(embed, guild)
