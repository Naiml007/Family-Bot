"""Structured logging and correlation ID management."""

from __future__ import annotations

import logging
import sys
import uuid
from contextvars import ContextVar

import structlog
from structlog.types import EventDict, Processor

_correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    """Return the active correlation ID for the current async context, if any."""
    return _correlation_id_var.get()


def set_correlation_id(correlation_id: str | None) -> None:
    """Bind a correlation ID to the current async context."""
    _correlation_id_var.set(correlation_id)


def new_correlation_id() -> str:
    """Generate a short correlation ID and bind it to the current async context."""
    cid = uuid.uuid4().hex[:12]
    _correlation_id_var.set(cid)
    return cid


def _inject_correlation_id(
    _logger: object,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    cid = _correlation_id_var.get()
    if cid is not None and "correlation_id" not in event_dict:
        event_dict["correlation_id"] = cid
    return event_dict


def configure_logging(*, env: str, log_level: str) -> None:
    """Configure structlog and stdlib logging for dev (pretty) or prod (JSON)."""
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        _inject_correlation_id,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if env == "prod"
        else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Keep noisy third-party loggers at INFO or WARNING unless debugging explicitly.
    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
