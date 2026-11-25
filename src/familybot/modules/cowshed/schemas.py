"""DTOs for the Cow Shed module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CowShedDTO:
    fed_at: datetime | None
    collect_at: datetime | None
    collect_due: bool


@dataclass(frozen=True, slots=True)
class CollectResult:
    due: bool
    collect_at: datetime | None
