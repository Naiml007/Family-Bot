import discord

from thesnow.core.embeds import stamp_embed
from thesnow.shared.constants import MAX_EMBED_FIELD_CHARS, PURPLE
from thesnow.shared.validation import bar, clip

from .service import LoanRecord


def _format_loan(loan: LoanRecord) -> str:
    remaining = loan.total - loan.paid
    pct = round(100 * loan.paid / loan.total) if loan.total > 0 else 0
    return (
        f"`#{loan.loan_id}` **{loan.party[:30]}** — **${remaining:,}** left "
        f"(`{bar(loan.paid, loan.total, 6)}` {pct}% paid)"
    )


def build_finance_panel_embed(loans: list[LoanRecord], guild: discord.Guild | None = None) -> discord.Embed:
    """Build the persistent Finance & Loans panel embed."""
    taken = [loan for loan in loans if loan.direction == "taken"]
    given = [loan for loan in loans if loan.direction == "given"]
    owed_pay = sum(loan.total - loan.paid for loan in taken)
    owed_us = sum(loan.total - loan.paid for loan in given)

    embed = discord.Embed(
        title="🏦  F I N A N C E   &   L O A N S  🏦",
        color=PURPLE,
        description="━━━━━━━━━━━━━━━━━━━━━━\n*Active family loans & repayment tracker*\n━━━━━━━━━━━━━━━━━━━━━━",
    )
    embed.add_field(name="💸 Total We Must Pay", value=f"**${owed_pay:,}**")
    embed.add_field(name="📥 Total Owed To Us", value=f"**${owed_us:,}**")
    embed.add_field(
        name="🔴 Loans We Took",
        value=clip([_format_loan(loan) for loan in taken], limit=12, max_chars=MAX_EMBED_FIELD_CHARS)
        if taken
        else "No active loans taken.",
        inline=False,
    )
    embed.add_field(
        name="🟢 Loans We Gave",
        value=clip([_format_loan(loan) for loan in given], limit=12, max_chars=MAX_EMBED_FIELD_CHARS)
        if given
        else "No active loans given.",
        inline=False,
    )
    return stamp_embed(embed, guild)
