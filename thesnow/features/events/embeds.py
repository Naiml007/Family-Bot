import discord

from thesnow.shared.constants import BLUE, MAX_EMBED_DESC_CHARS
from thesnow.shared.time import uk_str
from thesnow.shared.validation import clip

from .service import EventRecord


def build_events_list_embed(rows: list[EventRecord]) -> discord.Embed:
    """Build the upcoming events embed clipped to Discord description limits."""
    lines = [f"`#{ev.event_id}` **{ev.title}** — {uk_str(ev.start_ts)}" for ev in rows]
    desc = clip(lines, limit=50, max_chars=MAX_EMBED_DESC_CHARS) if lines else "No upcoming events."
    return discord.Embed(title="📅 Upcoming events (UK)", description=desc, color=BLUE)
