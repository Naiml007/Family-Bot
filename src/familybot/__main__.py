"""CLI / module entrypoint: `python -m familybot`."""

from __future__ import annotations

import asyncio

import structlog

from familybot.app import FamilyBot
from familybot.core.config import get_settings
from familybot.core.logging import configure_logging
from familybot.db.base import create_engine_and_sessionmaker
from familybot.observability.health import HealthServer

log = structlog.get_logger()


async def run() -> None:
    """Boot DB pool, /healthz server, and Discord bot."""
    settings = get_settings()
    configure_logging(env=settings.ENV, log_level=settings.LOG_LEVEL)

    token = settings.DISCORD_TOKEN.get_secret_value()
    if not token or token in {"unset", "your-discord-bot-token-here"}:
        raise RuntimeError("DISCORD_TOKEN must be configured before starting the bot.")
    if settings.DATABASE_URL is None:
        raise RuntimeError("DATABASE_URL must be configured before starting the bot.")

    engine, session_factory = create_engine_and_sessionmaker(
        settings.DATABASE_URL.get_secret_value()
    )
    bot = FamilyBot(settings=settings, engine=engine, session_factory=session_factory)
    health_server = HealthServer(
        host=settings.HEALTH_HOST,
        port=settings.HEALTH_PORT,
        probe=bot.health_probe,
    )

    log.info("bot.starting", env=settings.ENV, version=settings.VERSION)
    await health_server.start()
    try:
        async with bot:
            await bot.start(token)
    finally:
        await health_server.stop()
        await engine.dispose()
        log.info("bot.stopped")


def main() -> None:
    """Synchronous entrypoint."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
