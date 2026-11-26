import discord

from thesnow.core.embeds import stamp_embed
from thesnow.shared.constants import MAX_EMBED_FIELD_CHARS, RED
from thesnow.shared.validation import clip

from .service import ArmoryRow


def build_armory_panel_embed(rows: list[ArmoryRow], guild: discord.Guild | None = None) -> discord.Embed:
    """Build the persistent Family Armory panel embed."""
    weapons = [row for row in rows if row.weapon != "Vest"]
    vest = next((row for row in rows if row.weapon == "Vest"), None)

    weapon_lines: list[str] = []
    for row in weapons:
        ammo_txt = f" | 🔸 **{row.ammo:,}** ammo" if row.weapon not in ("Police Baton", "Balaclava") else ""
        weapon_lines.append(f"▪️ **{row.weapon}** — `{row.qty}` pcs{ammo_txt}")

    vest_qty = vest.qty if vest else 0
    embed = discord.Embed(
        title="🔫  F A M I L Y   A R M O R Y  🔫",
        color=RED,
        description="━━━━━━━━━━━━━━━━━━━━━━\n*Live weapon, ammo & vest stock status*\n━━━━━━━━━━━━━━━━━━━━━━",
    )
    embed.add_field(name="🛡️ Body Armor", value=f"🛡️ **Vest** — `{vest_qty}` pcs", inline=False)
    embed.add_field(
        name="🔫 Weapons & Ammunition",
        value=clip(weapon_lines, limit=25, max_chars=MAX_EMBED_FIELD_CHARS),
        inline=False,
    )
    return stamp_embed(embed, guild)
