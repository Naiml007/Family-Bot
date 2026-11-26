from typing import Any

import discord

from thesnow.core.context import AppContext
from thesnow.core.embeds import log_embed
from thesnow.core.errors import BaseModal, BaseView, safe_reply
from thesnow.core.forms import make_select_label, make_text_label
from thesnow.shared.constants import DEFAULT_ARMORY, GREEN, RED
from thesnow.shared.validation import Oops, num

from .service import mutate_armory

_NON_VEST_WEAPONS: tuple[str, ...] = tuple(sorted(w for w, _, _ in DEFAULT_ARMORY if w != "Vest"))


class ArmoryModal(BaseModal):
    """Modal collecting weapon choice, weapon/ammo/vest quantities, and optional take reason."""

    def __init__(self, ctx: AppContext, mode: str) -> None:
        super().__init__(title="Armory – Add Stock" if mode == "add" else "Armory – Take Stock")
        self.ctx = ctx
        self.mode = mode
        w_label, self.weapon_select = make_select_label(
            "Select Weapon",
            _NON_VEST_WEAPONS,
            placeholder="Pick a weapon...",
        )
        wq_label, self.w_qty_input = make_text_label("Weapon Quantity (0 if none)", default="0", max_length=20)
        aq_label, self.a_qty_input = make_text_label("Ammo Quantity (0 if none)", default="0", max_length=20)
        vq_label, self.v_qty_input = make_text_label("Vest Quantity (0 if none)", default="0", max_length=20)
        self.add_item(w_label)
        self.add_item(wq_label)
        self.add_item(aq_label)
        self.add_item(vq_label)

        self.reason_input: discord.ui.TextInput[Any] | None = None
        if mode == "use":
            r_label, self.reason_input = make_text_label("Reason for taking", max_length=200)
            self.add_item(r_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "armory:mutate"):
            return
        if interaction.guild is None:
            raise Oops("This command can only be used inside a server.")

        weapon = self.weapon_select.values[0] if self.weapon_select.values else ""
        if weapon not in _NON_VEST_WEAPONS:
            raise Oops("Please choose a valid weapon.")

        try:
            weapon_qty = num(self.w_qty_input.value, zero=True)
            ammo_qty = num(self.a_qty_input.value, zero=True)
            vest_qty = num(self.v_qty_input.value, zero=True)
        except ValueError as ex:
            raise Oops("Quantities must be whole numbers (0 or higher).") from ex

        reason = self.reason_input.value.strip() if self.reason_input is not None else "—"
        if self.mode == "use" and not reason:
            raise Oops("Please provide a reason for taking from the armory.")

        await interaction.response.defer(ephemeral=True)
        await mutate_armory(
            self.ctx.db,
            interaction.guild.id,
            weapon=weapon,
            mode=self.mode,
            weapon_qty=weapon_qty,
            ammo_qty=ammo_qty,
            vest_qty=vest_qty,
        )

        fields: dict[str, object] = {
            "Weapon": f"{weapon} (×{weapon_qty})" if weapon_qty > 0 else "—",
            "Ammo": f"{ammo_qty:,} pcs",
            "Vest": f"×{vest_qty}" if vest_qty > 0 else "0",
        }
        if self.mode == "use":
            fields["Reason"] = reason

        await self.ctx.panels.send_log(
            interaction.guild,
            "armory",
            log_embed(
                "🔫 Armory – Added" if self.mode == "add" else "🔫 Armory – Taken",
                GREEN if self.mode == "add" else RED,
                interaction.user,
                fields,
            ),
        )
        await self.ctx.panels.refresh(interaction.guild, "armory")
        verb = "Added to" if self.mode == "add" else "Taken from"
        await safe_reply(
            interaction,
            f"✅ {verb} armory: {weapon} (×{weapon_qty}), {ammo_qty:,} ammo, {vest_qty} vest.",
        )


class ArmoryView(BaseView):
    """Persistent Family Armory panel view."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="Add to Armory", emoji="📥", style=discord.ButtonStyle.success, custom_id="arm:add")
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "armory:mutate"):
            return
        await interaction.response.send_modal(ArmoryModal(self.ctx, "add"))

    @discord.ui.button(label="Use / Take", emoji="📤", style=discord.ButtonStyle.danger, custom_id="arm:use")
    async def use(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "armory:mutate"):
            return
        await interaction.response.send_modal(ArmoryModal(self.ctx, "use"))
