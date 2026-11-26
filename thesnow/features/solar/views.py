import time
from typing import Any

import discord

from thesnow.core.context import AppContext
from thesnow.core.embeds import log_embed
from thesnow.core.errors import BaseModal, BaseView, safe_reply
from thesnow.core.forms import make_text_label
from thesnow.shared.constants import GOLD, GREEN, RED
from thesnow.shared.time import uk_str
from thesnow.shared.validation import Oops, num

from .service import add_batteries, sell_batteries, use_batteries


class SolarAddModal(BaseModal):
    """Modal for adding solar batteries."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(title="Add Batteries")
        self.ctx = ctx
        qty_label, self.qty_input = make_text_label("How many batteries were added?", max_length=20)
        note_label, self.note_input = make_text_label("Note (optional)", required=False, max_length=250)
        self.add_item(qty_label)
        self.add_item(note_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "solar:mutate"):
            return
        if interaction.guild is None:
            raise Oops("This command can only be used inside a server.")
        try:
            qty = num(self.qty_input.value)
        except ValueError as ex:
            raise Oops("Please enter a valid positive whole number for battery count.") from ex

        note = self.note_input.value.strip()
        await interaction.response.defer(ephemeral=True)
        stock = await add_batteries(
            self.ctx.db,
            interaction.guild.id,
            qty=qty,
            note=note,
            who=interaction.user.display_name,
        )
        await self.ctx.panels.send_log(
            interaction.guild,
            "solar",
            log_embed(
                "🔋 Batteries Added",
                GREEN,
                interaction.user,
                {"Added": qty, "Note": note, "In Stock Now": stock},
            ),
        )
        await self.ctx.panels.refresh(interaction.guild, "solar")
        await safe_reply(interaction, f"✅ Added **{qty:,}** batteries. In stock: **{stock:,}**.")


class SolarUseModal(BaseModal):
    """Modal for consuming solar batteries."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(title="Use Batteries")
        self.ctx = ctx
        qty_label, self.qty_input = make_text_label("How many batteries were used?", max_length=20)
        desc_label, self.desc_input = make_text_label("What were the batteries used on?", max_length=250)
        self.add_item(qty_label)
        self.add_item(desc_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "solar:mutate"):
            return
        if interaction.guild is None:
            raise Oops("This command can only be used inside a server.")
        try:
            qty = num(self.qty_input.value)
        except ValueError as ex:
            raise Oops("Please enter a valid positive whole number for battery count.") from ex

        desc = self.desc_input.value.strip()
        if not desc:
            raise Oops("Please enter what the batteries were used on.")

        await interaction.response.defer(ephemeral=True)
        stock = await use_batteries(
            self.ctx.db,
            interaction.guild.id,
            qty=qty,
            desc=desc,
            who=interaction.user.display_name,
        )
        await self.ctx.panels.send_log(
            interaction.guild,
            "solar",
            log_embed(
                "🟠 Batteries Used",
                RED,
                interaction.user,
                {"Used": qty, "Used On (Description)": desc, "In Stock Now": stock},
            ),
        )
        await self.ctx.panels.refresh(interaction.guild, "solar")
        await safe_reply(interaction, f"✅ Logged **{qty:,}** batteries used. In stock: **{stock:,}**.")


class SolarSellModal(BaseModal):
    """Modal for selling solar batteries."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(title="Sell Batteries")
        self.ctx = ctx
        qty_label, self.qty_input = make_text_label("Number of batteries sold", max_length=20)
        price_label, self.price_input = make_text_label("Price per battery ($)", max_length=20)
        self.add_item(qty_label)
        self.add_item(price_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "solar:mutate"):
            return
        if interaction.guild is None:
            raise Oops("This command can only be used inside a server.")
        try:
            qty = num(self.qty_input.value)
            price = num(self.price_input.value)
        except ValueError as ex:
            raise Oops("Please enter valid positive whole numbers for quantity and price.") from ex

        total_sale = qty * price
        await interaction.response.defer(ephemeral=True)
        stock = await sell_batteries(
            self.ctx.db,
            interaction.guild.id,
            qty=qty,
            price=price,
            who=interaction.user.display_name,
        )
        await self.ctx.panels.send_log(
            interaction.guild,
            "solar",
            log_embed(
                "💰 Batteries Sold",
                GOLD,
                interaction.user,
                {
                    "Batteries Sold": qty,
                    "Price Each": f"${price:,}",
                    "Total Sale": f"${total_sale:,}",
                    "In Stock Now": stock,
                },
            ),
        )
        await self.ctx.panels.refresh(interaction.guild, "solar")
        await safe_reply(
            interaction,
            f"✅ Sold **{qty:,}** batteries for **${total_sale:,}**. In stock: **{stock:,}**.",
        )


class SolarView(BaseView):
    """Persistent Solar Plantation panel view."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="Added", emoji="➕", style=discord.ButtonStyle.success, custom_id="solar:add", row=0)
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "solar:mutate"):
            return
        await interaction.response.send_modal(SolarAddModal(self.ctx))

    @discord.ui.button(label="Used", emoji="➖", style=discord.ButtonStyle.danger, custom_id="solar:use", row=0)
    async def use(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "solar:mutate"):
            return
        await interaction.response.send_modal(SolarUseModal(self.ctx))

    @discord.ui.button(label="Sold", emoji="💰", style=discord.ButtonStyle.primary, custom_id="solar:sell", row=0)
    async def sell(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "solar:mutate"):
            return
        await interaction.response.send_modal(SolarSellModal(self.ctx))

    @discord.ui.button(
        label="Mark Repaired",
        emoji="🔧",
        style=discord.ButtonStyle.secondary,
        custom_id="solar:rep",
        row=1,
    )
    async def repaired(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "solar:mutate"):
            return
        if interaction.guild is None:
            return
        now_ts = int(time.time())
        await interaction.response.defer(ephemeral=True)
        await self.ctx.config.set(interaction.guild.id, "solar_last_repair", now_ts)
        await self.ctx.panels.send_log(
            interaction.guild,
            "solar",
            log_embed("🔧 Solar Repaired", GREEN, interaction.user, {"Time (UK)": uk_str(now_ts)}, now_ts=now_ts),
        )
        await self.ctx.panels.refresh(interaction.guild, "solar")
        await safe_reply(interaction, f"✅ Solar repair logged ({uk_str(now_ts)}).")
