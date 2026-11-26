import discord

from thesnow.core.embeds import stamp_embed
from thesnow.shared.constants import BLUE, GOLD, GREEN, MAX_EMBED_DESC_CHARS, MAX_EMBED_FIELD_CHARS, RED
from thesnow.shared.validation import bar, clip

from .service import BalanceEntry, BalanceStats


def format_tx_lines(entries: list[BalanceEntry]) -> list[str]:
    """Render balance ledger entries as Discord-safe markdown lines."""
    lines: list[str] = []
    for entry in entries:
        what = entry.detail[:40]
        if entry.kind == "add":
            lines.append(f"🟢 **+${entry.amount:,}** · {what} · {entry.who} · <t:{entry.ts}:R>")
        else:
            lines.append(f"🔴 **-${entry.amount:,}** · {what} · {entry.who} · <t:{entry.ts}:R>")
    return lines


def build_balance_panel_embed(stats: BalanceStats, guild: discord.Guild | None = None) -> discord.Embed:
    """Build the persistent Family Vault panel embed."""
    bal = stats.balance
    total_in = stats.total_in

    def _share(part: int) -> str:
        pct = round(100 * part / total_in) if total_in else 0
        return f"`{bar(part, total_in)}` {pct}%"

    embed = discord.Embed(
        title="💎  F A M I L Y   V A U L T  💎",
        color=GREEN if bal > 0 else RED,
        description=(
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "### 💰 Available Balance\n"
            f"# ${bal:,}\n"
            "━━━━━━━━━━━━━━━━━━━━━━"
        ),
    )
    embed.add_field(name="🐄 Cow Shed", value=f"**${stats.cow_shed:,}**\n{_share(stats.cow_shed)}")
    embed.add_field(name="🌱 Plantation", value=f"**${stats.plantation:,}**\n{_share(stats.plantation)}")
    embed.add_field(name="📦 Other", value=f"**${stats.other:,}**\n{_share(stats.other)}")
    embed.add_field(name="📈 Total In", value=f"**${total_in:,}**")
    embed.add_field(name="📉 Total Out", value=f"**${stats.total_out:,}**")
    embed.add_field(name="🧾 Transactions", value=f"**{stats.tx_count}**")
    recent_text = (
        clip(format_tx_lines(stats.recent), limit=5, max_chars=MAX_EMBED_FIELD_CHARS)
        if stats.tx_count
        else "No transactions yet"
    )
    embed.add_field(name="🕘 Recent Activity", value=recent_text, inline=False)
    return stamp_embed(embed, guild)


def build_check_balance_embed(total: int, guild: discord.Guild | None = None) -> discord.Embed:
    """Build the ephemeral available-balance embed."""
    embed = discord.Embed(title="💰 Available Balance", description=f"# ${total:,}", color=GOLD)
    return stamp_embed(embed, guild)


def build_history_embed(stats: BalanceStats, guild: discord.Guild | None = None) -> discord.Embed:
    """Build the ephemeral recent-transactions embed."""
    desc = (
        clip(format_tx_lines(stats.recent), limit=10, max_chars=MAX_EMBED_DESC_CHARS)
        if stats.tx_count
        else "Nothing yet."
    )
    embed = discord.Embed(title="📜 Last 10 Transactions", color=BLUE, description=desc)
    return stamp_embed(embed, guild)
