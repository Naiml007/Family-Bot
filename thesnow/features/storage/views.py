from typing import Any

import discord

from thesnow.core.context import AppContext
from thesnow.core.embeds import log_embed
from thesnow.core.errors import BaseModal, BaseView, safe_reply
from thesnow.core.forms import extract_modal_attachment, make_file_label, make_text_label
from thesnow.shared.constants import GREEN, RED
from thesnow.shared.validation import Oops, normalize_item_name, normalize_plate, num

from .embeds import build_storage_lookup_embed
from .service import find_storage_item, mutate_storage, update_storage_image


class StorageModal(BaseModal):
    """Modal collecting storage item, quantity, optional plate/reason, and screenshot proof."""

    def __init__(self, ctx: AppContext, mode: str, place: str) -> None:
        title = f"{'Store' if mode == 'add' else 'Take'} Items ({place})"[:45]
        super().__init__(title=title)
        self.ctx = ctx
        self.mode = mode
        self.place = place

        self.plate_input: discord.ui.TextInput[Any] | None = None
        if place == "Vehicle":
            plate_label, self.plate_input = make_text_label(
                "Last 3 digits of Vehicle Plate",
                placeholder="e.g. 482",
                max_length=10,
            )
            self.add_item(plate_label)

        item_label, self.item_input = make_text_label("Item Name", max_length=100)
        qty_label, self.qty_input = make_text_label("Quantity", placeholder="e.g. 10", max_length=20)
        self.add_item(item_label)
        self.add_item(qty_label)

        self.reason_input: discord.ui.TextInput[Any] | None = None
        if mode == "use":
            rsn_label, self.reason_input = make_text_label("Reason for taking", max_length=200)
            self.add_item(rsn_label)

        proof_label, self.proof_upload = make_file_label("Attach Screenshot Proof")
        self.add_item(proof_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "storage:mutate"):
            return
        if interaction.guild is None:
            raise Oops("This command can only be used inside a server.")

        if self.place == "Vehicle":
            plate = normalize_plate(self.plate_input.value if self.plate_input else "")
            loc_label = f"Vehicle ({plate})"
        else:
            loc_label = "Warehouse"

        item_name = normalize_item_name(self.item_input.value)
        try:
            qty = num(self.qty_input.value)
        except ValueError as ex:
            raise Oops("Please enter a valid positive whole number for quantity.") from ex

        reason = self.reason_input.value.strip() if self.reason_input is not None else ""
        if self.mode == "use" and not reason:
            raise Oops("Please enter a reason for taking items.")

        await interaction.response.defer(ephemeral=True)
        proof = await extract_modal_attachment(self.proof_upload, required=True)
        assert proof is not None

        canonical_item, new_qty, changed_from = await mutate_storage(
            self.ctx.db,
            interaction.guild.id,
            item=item_name,
            qty=qty,
            mode=self.mode,
            location=loc_label,
            who=interaction.user.display_name,
            img_url=proof.fallback_url,
        )

        fields: dict[str, object] = {
            "Item": canonical_item,
            "Qty Stored" if self.mode == "add" else "Qty Taken": qty,
            "Location": loc_label,
        }
        if self.mode == "use":
            fields["Reason"] = reason
        fields["New Stock"] = new_qty

        log_msg = await self.ctx.panels.send_log(
            interaction.guild,
            "storage",
            log_embed(
                "📦 Storage – Items Stored" if self.mode == "add" else "📦 Storage – Items Taken",
                GREEN if self.mode == "add" else RED,
                interaction.user,
                fields,
                image_url=f"attachment://{proof.filename}",
            ),
            file=proof.to_discord_file(),
        )
        if log_msg is not None and log_msg.attachments:
            await update_storage_image(
                self.ctx.db,
                interaction.guild.id,
                canonical_item,
                log_msg.attachments[0].url,
            )

        await self.ctx.panels.refresh(interaction.guild, "storage")
        verb = "Stored" if self.mode == "add" else "Took"
        note = f" (recorded location updated from `{changed_from}`)" if changed_from else ""
        await safe_reply(
            interaction,
            f"✅ {verb} **{qty:,} × {canonical_item}** at `{loc_label}`{note}. Stock now: **{new_qty:,}**.",
        )


class StoragePlaceView(BaseView):
    """Ephemeral location selector before opening the storage modal."""

    def __init__(self, ctx: AppContext, mode: str) -> None:
        super().__init__(timeout=60)
        self.ctx = ctx
        self.mode = mode

    @discord.ui.button(label="Warehouse", emoji="🏭", style=discord.ButtonStyle.primary)
    async def warehouse(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "storage:mutate"):
            return
        await interaction.response.send_modal(StorageModal(self.ctx, self.mode, "Warehouse"))

    @discord.ui.button(label="Vehicle", emoji="🚗", style=discord.ButtonStyle.secondary)
    async def vehicle(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "storage:mutate"):
            return
        await interaction.response.send_modal(StorageModal(self.ctx, self.mode, "Vehicle"))


class StorageFindModal(BaseModal):
    """Modal collecting an item search query for Shared Storage."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(title="Find Item in Storage")
        self.ctx = ctx
        q_label, self.query_input = make_text_label("Enter Item Name to search", max_length=100)
        self.add_item(q_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self.ctx.permissions.authorize(interaction, "storage:read"):
            return
        if interaction.guild is None:
            raise Oops("This command can only be used inside a server.")
        item = await find_storage_item(self.ctx.db, interaction.guild.id, self.query_input.value)
        await safe_reply(interaction, embed=build_storage_lookup_embed(item), ephemeral=True)


class StorageView(BaseView):
    """Persistent Shared Storage panel view."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(
        label="I Stored Items",
        emoji="📥",
        style=discord.ButtonStyle.success,
        custom_id="sto:add",
        row=0,
    )
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "storage:mutate"):
            return
        place_view = StoragePlaceView(self.ctx, "add")
        await interaction.response.send_message(
            "Where did you store the items?",
            view=place_view,
            ephemeral=True,
        )
        place_view.ephemeral_message = await interaction.original_response()

    @discord.ui.button(label="I Took Items", emoji="📤", style=discord.ButtonStyle.danger, custom_id="sto:use", row=0)
    async def use(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "storage:mutate"):
            return
        place_view = StoragePlaceView(self.ctx, "use")
        await interaction.response.send_message(
            "Where did you take the items from?",
            view=place_view,
            ephemeral=True,
        )
        place_view.ephemeral_message = await interaction.original_response()

    @discord.ui.button(label="Find Item", emoji="🔍", style=discord.ButtonStyle.primary, custom_id="sto:find", row=0)
    async def find(self, interaction: discord.Interaction, button: discord.ui.Button[Any]) -> None:
        if not await self.ctx.permissions.authorize(interaction, "storage:read"):
            return
        await interaction.response.send_modal(StorageFindModal(self.ctx))
