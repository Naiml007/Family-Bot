from typing import Any

import discord

from thesnow.core.context import AppContext
from thesnow.core.embeds import log_embed
from thesnow.core.errors import BaseModal, BaseView, safe_reply
from thesnow.core.forms import extract_modal_attachment, make_file_label, make_text_label
from thesnow.shared.constants import GOLD, GREEN
from thesnow.shared.validation import Oops, num

from .service import create_loan, pay_loan


class LoanCreateModal(BaseModal):
    """Modal creating a taken or given loan record."""

    def __init__(self, ctx: AppContext, direction: str) -> None:
        super().__init__(title="New Loan")
        self.ctx = ctx
        self.direction = direction
        who_label = (
            "Name of person we took loan from"
            if direction == "taken"
            else "Name of borrower (who owes us)"
        )
        p_label, self.party_input = make_text_label(who_label, max_length=100)
        a_label, self.amount_input = make_text_label("Loan Amount ($)", placeholder="e.g. 50000", max_length=20)
        n_label, self.note_input = make_text_label("Note (optional)", required=False, max_length=250)
        self.add_item(p_label)
        self.add_item(a_label)
        self.add_item(n_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "finance:mutate"):
            return
        if interaction.guild is None:
            raise Oops("This command can only be used inside a server.")
        party = self.party_input.value.strip()
        if not party:
            raise Oops("Please enter a person or organization name.")
        try:
            amount = num(self.amount_input.value)
        except ValueError as ex:
            raise Oops("Please enter a valid positive whole number for loan amount.") from ex

        note = self.note_input.value.strip()
        await interaction.response.defer(ephemeral=True)
        loan_id = await create_loan(
            self.ctx.db,
            interaction.guild.id,
            party=party,
            direction=self.direction,
            amount=amount,
            note=note,
        )
        title = "💸 Loan Taken" if self.direction == "taken" else "📥 Loan Given"
        await self.ctx.panels.send_log(
            interaction.guild,
            "finance",
            log_embed(
                title,
                GOLD,
                interaction.user,
                {"Loan ID": f"#{loan_id}", "Person / Org": party, "Amount": f"${amount:,}", "Note": note},
            ),
        )
        await self.ctx.panels.refresh(interaction.guild, "finance")
        await safe_reply(interaction, f"✅ Recorded {title.lower()} `#{loan_id}` ({party}) for **${amount:,}**.")


class LoanPayModal(BaseModal):
    """Modal recording a loan payment with mandatory screenshot proof."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(title="Pay Loan")
        self.ctx = ctx
        p_label, self.party_input = make_text_label("Name of person (or Loan #ID)", max_length=100)
        a_label, self.amount_input = make_text_label("Amount Paid ($)", max_length=20)
        proof_label, self.proof_upload = make_file_label("Attach Screenshot Proof of Payment")
        self.add_item(p_label)
        self.add_item(a_label)
        self.add_item(proof_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "finance:mutate"):
            return
        if interaction.guild is None:
            raise Oops("This command can only be used inside a server.")
        try:
            amount = num(self.amount_input.value)
        except ValueError as ex:
            raise Oops("Please enter a valid positive whole number for amount paid.") from ex

        await interaction.response.defer(ephemeral=True)
        proof = await extract_modal_attachment(self.proof_upload, required=True)
        assert proof is not None

        loan, remaining, multiple = await pay_loan(
            self.ctx.db,
            interaction.guild.id,
            query=self.party_input.value,
            amount=amount,
        )
        await self.ctx.panels.send_log(
            interaction.guild,
            "finance",
            log_embed(
                "✅ Loan Payment",
                GREEN,
                interaction.user,
                {
                    "Loan ID": f"#{loan.loan_id}",
                    "Name": loan.party,
                    "Amount Paid": f"${amount:,}",
                    "Paid By": interaction.user.display_name,
                    "Remaining": f"${remaining:,}",
                },
                image_url=f"attachment://{proof.filename}",
            ),
            file=proof.to_discord_file(),
        )
        await self.ctx.panels.refresh(interaction.guild, "finance")
        multi_note = " (oldest matching active loan selected)" if multiple else ""
        await safe_reply(
            interaction,
            f"✅ Applied **${amount:,}** to loan `#{loan.loan_id}` ({loan.party}){multi_note}. "
            f"Remaining: **${remaining:,}**.",
        )


class FinanceView(BaseView):
    """Persistent Finance & Loans panel view."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="Loan Taken", emoji="💸", style=discord.ButtonStyle.danger, custom_id="fin:taken")
    async def taken(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "finance:mutate"):
            return
        await interaction.response.send_modal(LoanCreateModal(self.ctx, "taken"))

    @discord.ui.button(label="Loan Given", emoji="📥", style=discord.ButtonStyle.primary, custom_id="fin:given")
    async def given(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "finance:mutate"):
            return
        await interaction.response.send_modal(LoanCreateModal(self.ctx, "given"))

    @discord.ui.button(label="Pay Loan", emoji="✅", style=discord.ButtonStyle.success, custom_id="fin:pay")
    async def pay(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "finance:mutate"):
            return
        await interaction.response.send_modal(LoanPayModal(self.ctx))
