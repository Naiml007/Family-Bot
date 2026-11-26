from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import discord

from thesnow.config import Settings
from thesnow.shared.ratelimit import UserCooldown

from .database import ConfigCache, Database
from .panels import PanelRegistry
from .permissions import PermissionService
from .scheduler import DeadlineScheduler

ReactionHandler = Callable[[discord.RawReactionActionEvent], Awaitable[None]]
TickHandler = Callable[[int], Awaitable[None]]


@dataclass
class AppContext:
    """Explicit dependency container wired once in the composition root."""

    settings: Settings
    db: Database
    config: ConfigCache
    permissions: PermissionService
    panels: PanelRegistry
    scheduler: DeadlineScheduler
    ticket_cooldowns: UserCooldown = field(default_factory=lambda: UserCooldown(30.0))
    closing_tickets: set[int] = field(default_factory=set)
    reaction_handlers: list[ReactionHandler] = field(default_factory=list)
    tick_handlers: list[TickHandler] = field(default_factory=list)
