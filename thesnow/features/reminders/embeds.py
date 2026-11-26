import discord

from thesnow.shared.constants import BLUE, MAX_EMBED_FIELD_CHARS, MAX_EMBED_FIELDS
from thesnow.shared.time import uk_str
from thesnow.shared.validation import truncate_text

from .service import ReminderRecord


def build_reminders_list_embed(rows: list[ReminderRecord]) -> discord.Embed:
    """Build the ephemeral custom reminders list respecting Discord's 25-field limit."""
    embed = discord.Embed(title="⏰ Reminders (UK time)", color=BLUE)
    if not rows:
        embed.description = "No custom reminders yet. Use `/reminder add`."
        return embed

    visible = rows[:MAX_EMBED_FIELDS]
    for rec in visible:
        value = (
            f"Every **{rec.interval_min / 60:g}h** → <@&{rec.role_id}> in <#{rec.channel_id}>\n"
            f"Next: **{uk_str(rec.next_run)}**"
        )
        embed.add_field(
            name=truncate_text(f"#{rec.reminder_id} · {rec.chapter}", 256),
            value=truncate_text(value, MAX_EMBED_FIELD_CHARS),
            inline=False,
        )
    if len(rows) > MAX_EMBED_FIELDS:
        embed.set_footer(text=f"Showing {MAX_EMBED_FIELDS} of {len(rows)} reminders.")
    return embed
