import io
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import discord

from thesnow.shared.constants import MAX_PROOF_BYTES
from thesnow.shared.validation import Oops, is_valid_image_attachment


@dataclass(frozen=True)
class ProofImage:
    """Validated screenshot attachment bytes ready for re-upload to a log embed."""

    data: bytes
    filename: str
    content_type: str
    fallback_url: str

    def to_discord_file(self) -> discord.File:
        """Create a fresh discord.File stream from stored attachment bytes."""
        return discord.File(io.BytesIO(self.data), filename=self.filename)


def make_text_label(
    label: str,
    *,
    placeholder: str | None = None,
    default: str | None = None,
    required: bool = True,
    max_length: int = 300,
    style: discord.TextStyle = discord.TextStyle.short,
    description: str | None = None,
) -> tuple[discord.ui.Label[Any], discord.ui.TextInput[Any]]:
    """Create a labeled TextInput component for discord.ui.Modal."""
    field: discord.ui.TextInput[Any] = discord.ui.TextInput(
        style=style,
        placeholder=placeholder,
        default=default,
        required=required,
        max_length=max_length,
    )
    wrapper: discord.ui.Label[Any] = discord.ui.Label(text=label[:45], description=description, component=field)
    return wrapper, field


def make_select_label(
    label: str,
    options: Sequence[str],
    *,
    placeholder: str = "Choose one...",
    description: str | None = None,
) -> tuple[discord.ui.Label[Any], discord.ui.Select[Any]]:
    """Create a labeled single-select dropdown component for discord.ui.Modal."""
    select: discord.ui.Select[Any] = discord.ui.Select(
        placeholder=placeholder,
        min_values=1,
        max_values=1,
        options=[discord.SelectOption(label=opt[:100], value=opt[:100]) for opt in options],
    )
    wrapper: discord.ui.Label[Any] = discord.ui.Label(text=label[:45], description=description, component=select)
    return wrapper, select


def make_file_label(
    label: str,
    *,
    description: str | None = "Upload a PNG, JPG, WEBP, or GIF screenshot (max 8 MB).",
    required: bool = True,
) -> tuple[discord.ui.Label[Any], discord.ui.FileUpload[Any]]:
    """Create a labeled FileUpload component for discord.ui.Modal."""
    upload: discord.ui.FileUpload[Any] = discord.ui.FileUpload(
        required=required,
        min_values=1 if required else 0,
        max_values=1,
    )
    wrapper: discord.ui.Label[Any] = discord.ui.Label(text=label[:45], description=description, component=upload)
    return wrapper, upload


async def extract_modal_attachment(
    upload: discord.ui.FileUpload[Any],
    *,
    required: bool = True,
) -> ProofImage | None:
    """Validate and download a screenshot uploaded through a Modal FileUpload component."""
    attachments = upload.values
    if not attachments:
        if required:
            raise Oops("Please attach a screenshot image.")
        return None

    att = attachments[0]
    if att.size > MAX_PROOF_BYTES:
        raise Oops("Screenshot must be 8 MB or smaller.")
    if not is_valid_image_attachment(att.content_type, att.filename, att.size):
        raise Oops("Please upload a valid image file (`.png`, `.jpg`, `.jpeg`, `.webp`, or `.gif`).")

    try:
        data = await att.read()
    except discord.HTTPException as ex:
        raise Oops("Could not download the uploaded screenshot from Discord. Please try again.") from ex

    if not data or len(data) > MAX_PROOF_BYTES:
        raise Oops("Uploaded image is empty or exceeds the 8 MB size limit.")

    return ProofImage(
        data=data,
        filename=att.filename or "proof.png",
        content_type=att.content_type or "image/png",
        fallback_url=att.url,
    )
