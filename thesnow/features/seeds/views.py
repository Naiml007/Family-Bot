from typing import Any

import discord

from thesnow.core.context import AppContext
from thesnow.core.embeds import log_embed
from thesnow.core.errors import BaseModal, BaseView, safe_reply
from thesnow.core.forms import make_select_label, make_text_label
from thesnow.shared.constants import GREEN, LOCATIONS, RED, SEED_EMOJI, SEEDS
from thesnow.shared.validation import Oops, num

from .service import get_single_seed_qty, mutate_seed_stock


class SeedModal(BaseModal):
    """Modal collecting seed quantity, location select, and optional note."""

    def __init__(self, ctx: AppContext, seed: str, mode: str) -> None:
        super().__init__(title=f"{'Add' if mode == 'add' else 'Use'} {seed}"[:45])
        self.ctx = ctx
        self.seed = seed
        self.mode = mode
        loc_label, self.loc_select = make_select_label(
            "Location",
            LOCATIONS,
            placeholder="Pick Plantation or Cow Shed",
        )
        qty_label, self.qty_input = make_text_label(f"How many {seed} seeds?", placeholder="e.g. 25", max_length=20)
        note_label, self.note_input = make_text_label("Note (optional)", required=False, max_length=250)
        self.add_item(loc_label)
        self.add_item(qty_label)
        self.add_item(note_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "seeds:mutate"):
            return
        if interaction.guild is None:
            raise Oops("This command can only be used inside a server.")

        try:
            qty = num(self.qty_input.value)
        except ValueError as ex:
            raise Oops("Please enter a valid positive whole number for quantity.") from ex

        loc = self.loc_select.values[0] if self.loc_select.values else LOCATIONS[0]
        if loc not in LOCATIONS:
            raise Oops("Please pick a valid location.")
        note = self.note_input.value.strip()
        delta = qty if self.mode == "add" else -qty

        await interaction.response.defer(ephemeral=True)
        new_stock = await mutate_seed_stock(self.ctx.db, interaction.guild.id, seed=self.seed, delta=delta)
        await self.ctx.panels.send_log(
            interaction.guild,
            "seeds",
            log_embed(
                f"{SEED_EMOJI[self.seed]} Seeds {'Added' if self.mode == 'add' else 'Used'} – {self.seed}",
                GREEN if self.mode == "add" else RED,
                interaction.user,
                {
                    "Seed": f"{SEED_EMOJI[self.seed]} {self.seed}",
                    "Qty": qty,
                    "Location": loc,
                    "Note": note,
                    "Stock now": new_stock,
                },
            ),
        )
        await self.ctx.panels.refresh(interaction.guild, "seeds")
        verb = "Added" if self.mode == "add" else "Used"
        await safe_reply(
            interaction,
            f"✅ {verb} **{qty:,} {self.seed}** ({loc}). Stock now: **{new_stock:,}**.",
        )


class SeedActionView(BaseView):
    """Ephemeral prompt choosing Add or Use for a specific seed."""

    def __init__(self, ctx: AppContext, seed: str) -> None:
        super().__init__(timeout=60)
        self.ctx = ctx
        self.seed = seed

    @discord.ui.button(label="Add Seeds", emoji="➕", style=discord.ButtonStyle.success)
    async def add_btn(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "seeds:mutate"):
            return
        await interaction.response.send_modal(SeedModal(self.ctx, self.seed, "add"))

    @discord.ui.button(label="Use Seeds", emoji="➖", style=discord.ButtonStyle.danger)
    async def use_btn(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "seeds:mutate"):
            return
        await interaction.response.send_modal(SeedModal(self.ctx, self.seed, "use"))


class _SeedPickButton(discord.ui.Button[Any]):
    """Button opening the action prompt for a single seed type."""

    def __init__(self, ctx: AppContext, seed: str, row: int) -> None:
        super().__init__(
            label=seed,
            emoji=SEED_EMOJI[seed],
            style=discord.ButtonStyle.secondary,
            custom_id=f"seed_pick:{seed}",
            row=row,
        )
        self.ctx = ctx
        self.seed = seed

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "seeds:mutate"):
            return
        if interaction.guild is None:
            return
        qty = await get_single_seed_qty(self.ctx.db, interaction.guild.id, self.seed)
        embed = discord.Embed(
            title=f"{SEED_EMOJI[self.seed]} {self.seed} Seeds",
            description=f"Current stock: **{qty:,} pcs**\nChoose an action below:",
            color=GREEN,
        )
        action_view = SeedActionView(self.ctx, self.seed)
        await interaction.response.send_message(embed=embed, view=action_view, ephemeral=True)
        action_view.ephemeral_message = await interaction.original_response()


class SeedsView(BaseView):
    """Persistent Seed Inventory panel view."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(timeout=None)
        self.ctx = ctx
        for idx, seed in enumerate(SEEDS):
            self.add_item(_SeedPickButton(ctx, seed, row=idx // 3))
