import time

import discord

from thesnow.core.embeds import stamp_embed
from thesnow.shared.constants import GOLD, GREEN, RED
from thesnow.shared.time import next_cow_slot, next_plant_slot, slot_label_from_key

from .service import ActiveAlert


def build_schedule_panel_embed(
    kind: str,
    *,
    alert: ActiveAlert | None,
    last_done: str | None,
    guild: discord.Guild | None = None,
    now_ts: float | None = None,
) -> discord.Embed:
    """Build the Cow Shed or Plantation live status panel embed."""
    ts = int(now_ts if now_ts is not None else time.time())
    is_due = alert is not None and alert.ack == 0

    if kind == "cowshed":
        nxt_ts, nxt_label = next_cow_slot(ts)
        title = "🐄  C O W   S H E D   T I M E R  🐄"
        task_name = "Cow Feed & Milking"
        sched_text = "`01:00` · `04:00` · `07:00` · `10:00` · `13:00` · `16:00` · `19:00` · `22:00` (UK)"
        base_color = GOLD
    else:
        nxt_ts, nxt_label = next_plant_slot(ts)
        title = "🌱  P L A N T A T I O N   T I M E R  🌱"
        task_name = "Nourish & Harvest"
        sched_text = "Every hour at `__:30` (UK Time)"
        base_color = GREEN

    if is_due and alert is not None:
        slot_time = slot_label_from_key(alert.slot_key)
        status_block = (
            f"### 🚨 {task_name.upper()} DUE NOW (`{slot_time} UK`)\n"
            "Click **✅ Mark Done** or react with ✅ on the ping message below to stop alerts!"
        )
        color = RED
    else:
        status_block = (
            f"### ⏳ Next {task_name}\n"
            f"# <t:{nxt_ts}:R>\n"
            f"Scheduled at **{nxt_label}** (<t:{nxt_ts}:t> your local time)"
        )
        color = base_color

    embed = discord.Embed(
        title=title,
        color=color,
        description=f"━━━━━━━━━━━━━━━━━━━━━━\n{status_block}\n━━━━━━━━━━━━━━━━━━━━━━",
    )
    embed.add_field(name="📅 Daily UK Schedule", value=sched_text, inline=False)
    embed.add_field(name="✅ Last Completed", value=last_done or "Not logged yet", inline=False)
    return stamp_embed(embed, guild, now_ts=ts)
