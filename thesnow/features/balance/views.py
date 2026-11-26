from typing import Any

import discord

from thesnow.core.context import AppContext
from thesnow.core.embeds import log_embed
from thesnow.core.errors import BaseModal, BaseView, safe_reply
from thesnow.core.forms import make_text_label
from thesnow.shared.constants import GREEN, RED
from thesnow.shared.validation import Oops, num

from .embeds import build_check_balance_embed, build_history_embed
from .service import deposit, get_balance_stats, get_balance_total, withdraw


class DepositModal(BaseModal):
    """Modal collecting deposit amount and optional custom source."""

    def __init__(self, ctx: AppContext, source: str | None = None) -> None:
        super().__init__(title=f"{source or 'Other'} Deposit"[:45])
        self.ctx = ctx
        self.fixed_source = source
        amt_label, self.amount_input = make_text_label("Amount ($)", placeholder="e.g. 2500", max_length=20)
        self.add_item(amt_label)
        self.source_input: discord.ui.TextInput[Any] | None = None
        if source is None:
            src_label, self.source_input = make_text_label(
                "From (where did the money come from?)",
                placeholder="e.g. Family event payout",
                max_length=150,
            )
            self.add_item(src_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "balance:deposit"):
            return
        if interaction.guild is None:
            raise Oops("This command can only be used inside a server.")

        try:
            amount = num(self.amount_input.value)
        except ValueError as ex:
            raise Oops("Please enter a valid positive whole number for Amount (e.g. 2500).") from ex

        source = self.fixed_source or (self.source_input.value.strip() if self.source_input else "")
        if not source:
            raise Oops("Please enter where the money came from.")

        await interaction.response.defer(ephemeral=True)
        new_balance = await deposit(
            self.ctx.db,
            interaction.guild.id,
            amount=amount,
            source=source[:150],
            who=interaction.user.display_name,
        )
        icon = {"Cow Shed": "🐄", "Plantation": "🌱"}.get(source, "➕")
        await self.ctx.panels.send_log(
            interaction.guild,
            "balance",
            log_embed(
                f"{icon} Deposit – {source}",
                GREEN,
                interaction.user,
                {"Amount": f"${amount:,}", "From": source, "New balance": f"${new_balance:,}"},
            ),
        )
        await self.ctx.panels.refresh(interaction.guild, "balance")
        await safe_reply(
            interaction,
            f"✅ Deposited **${amount:,}** ({source}). New balance: **${new_balance:,}**.",
        )


class WithdrawModal(BaseModal):
    """Modal collecting withdrawal details."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(title="Withdraw Money")
        self.ctx = ctx
        pid_label, self.pid_input = make_text_label("Your ID", placeholder="e.g. 12345", max_length=60)
        ign_label, self.ign_input = make_text_label("Your IGN (in-game name)", max_length=80)
        amt_label, self.amount_input = make_text_label("Amount ($)", placeholder="e.g. 2500", max_length=20)
        rsn_label, self.reason_input = make_text_label("Reason", max_length=200)
        self.add_item(pid_label)
        self.add_item(ign_label)
        self.add_item(amt_label)
        self.add_item(rsn_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "balance:withdraw"):
            return
        if interaction.guild is None:
            raise Oops("This command can only be used inside a server.")

        pid = self.pid_input.value.strip()
        ign = self.ign_input.value.strip()
        reason = self.reason_input.value.strip()
        if not pid or not ign or not reason:
            raise Oops("Player ID, IGN, and Reason cannot be empty.")

        try:
            amount = num(self.amount_input.value)
        except ValueError as ex:
            raise Oops("Please enter a valid positive whole number for Amount (e.g. 2500).") from ex

        await interaction.response.defer(ephemeral=True)
        new_balance = await withdraw(
            self.ctx.db,
            interaction.guild.id,
            amount=amount,
            pid=pid,
            ign=ign,
            reason=reason,
        )
        await self.ctx.panels.send_log(
            interaction.guild,
            "balance",
            log_embed(
                "➖ Withdrawal",
                RED,
                interaction.user,
                {
                    "Player ID": pid,
                    "IGN": ign,
                    "Amount": f"${amount:,}",
                    "Reason": reason,
                    "Discord": interaction.user.mention,
                    "New balance": f"${new_balance:,}",
                },
            ),
        )
        await self.ctx.panels.refresh(interaction.guild, "balance")
        await safe_reply(
            interaction,
            f"✅ Withdrew **${amount:,}**. New balance: **${new_balance:,}**.",
        )


class BalanceView(BaseView):
    """Persistent Family Vault panel view."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="Cow Shed", emoji="🐄", style=discord.ButtonStyle.success, custom_id="bal:cow", row=0)
    async def cow(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "balance:deposit"):
            return
        await interaction.response.send_modal(DepositModal(self.ctx, "Cow Shed"))

    @discord.ui.button(
        label="Plantation",
        emoji="🌱",
        style=discord.ButtonStyle.success,
        custom_id="bal:plant",
        row=0,
    )
    async def plant(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "balance:deposit"):
            return
        await interaction.response.send_modal(DepositModal(self.ctx, "Plantation"))

    @discord.ui.button(
        label="Other Deposit",
        emoji="➕",
        style=discord.ButtonStyle.primary,
        custom_id="bal:add",
        row=0,
    )
    async def other(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "balance:deposit"):
            return
        await interaction.response.send_modal(DepositModal(self.ctx))

    @discord.ui.button(label="Withdraw", emoji="➖", style=discord.ButtonStyle.danger, custom_id="bal:wd", row=1)
    async def withdraw_btn(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "balance:withdraw"):
            return
        await interaction.response.send_modal(WithdrawModal(self.ctx))

    @discord.ui.button(
        label="Check Balance",
        emoji="💰",
        style=discord.ButtonStyle.secondary,
        custom_id="bal:check",
        row=1,
    )
    async def check(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "balance:read"):
            return
        if interaction.guild is None:
            return
        total = await get_balance_total(self.ctx.db, interaction.guild.id)
        await safe_reply(interaction, embed=build_check_balance_embed(total, interaction.guild))

    @discord.ui.button(
        label="History",
        emoji="📜",
        style=discord.ButtonStyle.secondary,
        custom_id="bal:hist",
        row=1,
    )
    async def history(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "balance:read"):
            return
        if interaction.guild is None:
            return
        stats = await get_balance_stats(self.ctx.db, interaction.guild.id, recent_limit=10)
        await safe_reply(interaction, embed=build_history_embed(stats, interaction.guild))
