import asyncio
import time
from typing import Any

import discord

from thesnow.core.context import AppContext
from thesnow.core.embeds import log_embed
from thesnow.core.errors import BaseModal, BaseView, safe_reply
from thesnow.core.forms import make_text_label
from thesnow.shared.constants import BLUE, GREEN, RED
from thesnow.shared.time import uk_str
from thesnow.shared.validation import Oops, num

from .service import record_bonus_payout

MAX_OPEN_GUILD_TICKETS = 25


def _parse_ticket_owner_id(topic: str | None) -> int | None:
    if not topic or not topic.startswith("bonus_ticket:"):
        return None
    raw_id = topic.split(":", 1)[1].strip()
    return int(raw_id) if raw_id.isdigit() else None


class CloseView(BaseView):
    """Persistent Close Ticket button view inside bonus ticket channels."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="Close Ticket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel) or interaction.guild is None:
            await safe_reply(interaction, "⛔ Tickets can only be closed inside a ticket text channel.")
            return

        owner_id = _parse_ticket_owner_id(channel.topic)
        if owner_id is None:
            await safe_reply(interaction, "⛔ This channel is not an active bonus ticket.")
            return

        if not await self.ctx.permissions.authorize(
            interaction,
            "bonus:ticket_close",
            ticket_owner_id=owner_id,
        ):
            return

        if channel.id in self.ctx.closing_tickets:
            await safe_reply(interaction, "🔒 This ticket is already closing.")
            return

        self.ctx.closing_tickets.add(channel.id)
        try:
            await interaction.response.send_message("🔒 Closing in 5 seconds…")
            await self.ctx.panels.send_log(
                interaction.guild,
                "bonus_ticket",
                log_embed("🔒 Bonus Ticket Closed", RED, interaction.user, {"Channel": channel.name}),
            )
            await asyncio.sleep(5)
            try:
                await channel.delete()
            except discord.NotFound:
                pass
            except discord.Forbidden:
                await safe_reply(interaction, "⛔ Bot lacks permission to delete this ticket channel.")
        finally:
            self.ctx.closing_tickets.discard(channel.id)


class TicketModal(BaseModal):
    """Modal collecting bonus request amount and reason."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(title="Bonus Request")
        self.ctx = ctx
        a_label, self.amount_input = make_text_label("Bonus amount requested", max_length=80)
        r_label, self.reason_input = make_text_label(
            "Reason",
            style=discord.TextStyle.paragraph,
            max_length=300,
        )
        self.add_item(a_label)
        self.add_item(r_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "bonus:ticket_open"):
            return
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            raise Oops("This command can only be used inside a server.")

        amount_text = self.amount_input.value.strip()
        reason_text = self.reason_input.value.strip()
        if not amount_text or not reason_text:
            raise Oops("Amount and Reason cannot be empty.")

        existing = next(
            (ch for ch in guild.text_channels if ch.topic == f"bonus_ticket:{interaction.user.id}"),
            None,
        )
        if existing is not None:
            await safe_reply(interaction, f"You already have an open ticket: {existing.mention}")
            return

        open_tickets = sum(1 for ch in guild.text_channels if (ch.topic or "").startswith("bonus_ticket:"))
        if open_tickets >= MAX_OPEN_GUILD_TICKETS:
            raise Oops("Too many open bonus tickets right now. Please wait for leadership to close existing tickets.")

        await interaction.response.defer(ephemeral=True)
        overwrites: dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                attach_files=True,
                read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        pings: list[str] = []
        role_cfg = await self.ctx.config.get_many(guild.id, "mod_role", "deputy_role")
        for key in ("mod_role", "deputy_role"):
            rid = role_cfg.get(key)
            if rid and rid.isdigit():
                role = guild.get_role(int(rid))
                if role is not None:
                    overwrites[role] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                    )
                    pings.append(role.mention)

        category = interaction.channel.category if isinstance(interaction.channel, discord.TextChannel) else None
        ch_name = f"bonus-{interaction.user.name}"[:90]
        try:
            channel = await guild.create_text_channel(
                ch_name,
                category=category,
                overwrites=overwrites,
                topic=f"bonus_ticket:{interaction.user.id}",
            )
        except discord.Forbidden as ex:
            raise Oops("Bot lacks `Manage Channels` permission to create your ticket.") from ex
        except discord.HTTPException as ex:
            if category is None:
                raise Oops("Could not create a ticket channel right now.") from ex
            try:
                channel = await guild.create_text_channel(
                    ch_name,
                    overwrites=overwrites,
                    topic=f"bonus_ticket:{interaction.user.id}",
                )
            except discord.HTTPException as inner_ex:
                raise Oops("Could not create a ticket channel right now.") from inner_ex

        embed = discord.Embed(title="🎟️ Bonus Request", color=BLUE)
        embed.add_field(name="Requested by", value=interaction.user.mention)
        embed.add_field(name="Amount", value=amount_text)
        embed.add_field(name="Reason", value=reason_text, inline=False)
        embed.set_footer(text=f"Opened {uk_str(time.time())} (UK)")
        await channel.send(
            " ".join(pings) or None,
            embed=embed,
            view=CloseView(self.ctx),
            allowed_mentions=discord.AllowedMentions(roles=True),
        )
        await self.ctx.panels.send_log(
            guild,
            "bonus_ticket",
            log_embed(
                "🎟️ Bonus Ticket Opened",
                GREEN,
                interaction.user,
                {"Amount": amount_text, "Channel": channel.mention},
            ),
        )
        await safe_reply(interaction, f"✅ Your private ticket is ready: {channel.mention}")


class TicketView(BaseView):
    """Persistent Bonus Request ticket panel view."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(
        label="Create Bonus Request",
        emoji="🎟️",
        style=discord.ButtonStyle.primary,
        custom_id="ticket:new",
    )
    async def new(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "bonus:ticket_open"):
            return
        if interaction.guild is None:
            return
        for channel in interaction.guild.text_channels:
            if channel.topic == f"bonus_ticket:{interaction.user.id}":
                await safe_reply(interaction, f"You already have an open ticket: {channel.mention}")
                return

        remaining = self.ctx.ticket_cooldowns.check_and_consume(
            interaction.guild.id,
            interaction.user.id,
            "ticket:new",
        )
        if remaining > 0:
            await safe_reply(
                interaction,
                f"⏳ Please wait **{remaining:.0f}s** before opening another bonus request.",
            )
            return

        await interaction.response.send_modal(TicketModal(self.ctx))


class BonusLogModal(BaseModal):
    """Modal logging a paid bonus."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(title="Log Bonus")
        self.ctx = ctx
        to_label, self.to_input = make_text_label("Paid to (name)", max_length=100)
        amt_label, self.amount_input = make_text_label("Amount ($)", max_length=20)
        rsn_label, self.reason_input = make_text_label("Reason", max_length=200)
        self.add_item(to_label)
        self.add_item(amt_label)
        self.add_item(rsn_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "bonus:log"):
            return
        if interaction.guild is None:
            raise Oops("This command can only be used inside a server.")

        paid_to = self.to_input.value.strip()
        reason = self.reason_input.value.strip()
        if not paid_to or not reason:
            raise Oops("Paid-to name and Reason cannot be empty.")
        try:
            amount = num(self.amount_input.value)
        except ValueError as ex:
            raise Oops("Please enter a valid positive whole number for bonus amount.") from ex

        await interaction.response.defer(ephemeral=True)
        await record_bonus_payout(
            self.ctx.db,
            interaction.guild.id,
            paid_to=paid_to,
            amount=amount,
            reason=reason,
            who=interaction.user.display_name,
        )
        await self.ctx.panels.send_log(
            interaction.guild,
            "bonus_log",
            log_embed(
                "💵 Bonus Paid",
                GREEN,
                interaction.user,
                {"Paid to": paid_to, "Amount": f"${amount:,}", "Reason": reason},
            ),
        )
        await self.ctx.panels.refresh(interaction.guild, "bonus_log")
        await safe_reply(interaction, f"✅ Logged **${amount:,}** bonus paid to **{paid_to}**.")


class BonusLogView(BaseView):
    """Persistent Bonus Payout Logs panel view."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(
        label="Log Bonus Payment",
        emoji="💵",
        style=discord.ButtonStyle.success,
        custom_id="bonus:log",
    )
    async def log(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "bonus:log"):
            return
        await interaction.response.send_modal(BonusLogModal(self.ctx))
