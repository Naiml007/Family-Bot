from collections.abc import Sequence
from urllib.parse import urlparse

from .constants import (
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_HOSTS,
    MAX_AMOUNT,
    MAX_EMBED_FIELD_CHARS,
    MAX_PROOF_BYTES,
)


class Oops(Exception):
    """User-facing validation or state error message."""


def num(text: str, zero: bool = False, max_value: int = MAX_AMOUNT) -> int:
    """Parse a positive (or optionally zero) whole integer bounded by max_value."""
    cleaned = text.replace(",", "").replace("$", "").replace("#", "").strip()
    if not cleaned:
        raise ValueError("Empty number")
    value = int(cleaned)
    if value < 0 or (value == 0 and not zero) or value > max_value:
        raise ValueError("Number out of range")
    return value


def truncate_text(text: str, max_chars: int) -> str:
    """Truncate text cleanly to fit within max_chars."""
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars == 1:
        return "…"
    return f"{text[: max_chars - 1]}…"


def clip(lines: Sequence[str], limit: int = 12, max_chars: int = MAX_EMBED_FIELD_CHARS) -> str:
    """Join up to limit lines while respecting Discord character limits."""
    if not lines:
        return "—"

    kept: list[str] = []
    used = 0
    total = len(lines)
    capped = min(limit, total)

    for idx in range(capped):
        line = lines[idx]
        remaining = total - (idx + 1)
        suffix = f"\n…and {remaining} more" if remaining > 0 else ""
        sep_len = 1 if kept else 0
        projected = used + sep_len + len(line) + len(suffix)
        if projected <= max_chars:
            kept.append(line)
            used += sep_len + len(line)
            continue

        if not kept:
            reserve = len(suffix)
            budget = max(1, max_chars - reserve)
            kept.append(truncate_text(line, budget))
            if remaining > 0 and len(kept[0]) + len(suffix) <= max_chars:
                kept.append(suffix.lstrip("\n"))
            return "\n".join(kept)

        more_count = total - idx
        kept.append(f"…and {more_count} more")
        return "\n".join(kept)

    if total > capped:
        suffix_line = f"…and {total - capped} more"
        if used + 1 + len(suffix_line) <= max_chars:
            kept.append(suffix_line)
        elif kept:
            kept[-1] = f"…and {total - len(kept) + 1} more"
    return "\n".join(kept) or "—"


def bar(part: int, total: int, length: int = 10) -> str:
    """Render a compact unicode progress bar."""
    filled = round(length * part / total) if total else 0
    filled = max(0, min(length, filled))
    return "▰" * filled + "▱" * (length - filled)


def normalize_item_name(raw: str) -> str:
    """Normalize storage item names consistently across store/take/lookup operations."""
    collapsed = " ".join(raw.split())
    if not collapsed:
        raise Oops("Item name cannot be empty.")
    return collapsed.title()[:100]


def normalize_plate(raw: str) -> str:
    """Validate and normalize the last 3 alphanumeric license-plate characters."""
    plate = raw.strip().upper()
    if len(plate) != 3 or not plate.isalnum():
        raise Oops("Enter the exact **last 3 characters/digits** of the vehicle license plate (e.g. `482`).")
    return plate


def is_valid_image_attachment(content_type: str | None, filename: str, size: int) -> bool:
    """Validate an uploaded attachment's type, filename extension, and byte limit."""
    if size <= 0 or size > MAX_PROOF_BYTES:
        return False
    is_image_mime = (content_type or "").lower().startswith("image/")
    has_image_ext = filename.lower().endswith(ALLOWED_IMAGE_EXTENSIONS)
    return is_image_mime or has_image_ext


def is_allowed_discord_image_url(url: str | None) -> bool:
    """Allow only HTTPS Discord CDN image URLs or safe attachment:// references."""
    if not url:
        return False
    cleaned = url.strip()
    if cleaned.startswith("attachment://"):
        name = cleaned.removeprefix("attachment://")
        return bool(name) and "/" not in name and "\\" not in name and "?" not in name and "#" not in name
    parsed = urlparse(cleaned)
    return parsed.scheme == "https" and (parsed.hostname or "").lower() in ALLOWED_IMAGE_HOSTS
