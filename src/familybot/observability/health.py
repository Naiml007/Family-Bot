"""Lightweight aiohttp HTTP server exposing /healthz for Docker and uptime checks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import structlog
from aiohttp import web

log = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    """Payload returned by the /healthz probe."""

    ok: bool
    db_ok: bool
    db_latency_ms: float | None
    uptime_seconds: float
    version: str

    def to_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.ok else "degraded",
            "db": "ok" if self.db_ok else "error",
            "db_latency_ms": (
                round(self.db_latency_ms, 2) if self.db_latency_ms is not None else None
            ),
            "uptime_seconds": round(self.uptime_seconds, 1),
            "version": self.version,
        }


HealthProbe = Callable[[], Awaitable[HealthSnapshot]]


class HealthServer:
    """Manages the lifecycle of the /healthz HTTP endpoint."""

    def __init__(self, *, host: str, port: int, probe: HealthProbe) -> None:
        self._host = host
        self._port = port
        self._probe = probe
        self._app = web.Application()
        self._app.router.add_get("/healthz", self._handle_healthz)
        self._runner: web.AppRunner | None = None

    @property
    def app(self) -> web.Application:
        """Expose aiohttp Application for testing."""
        return self._app

    async def _handle_healthz(self, _request: web.Request) -> web.Response:
        snapshot = await self._probe()
        status = 200 if snapshot.ok else 503
        return web.json_response(snapshot.to_dict(), status=status)

    async def start(self) -> None:
        """Start listening for /healthz requests."""
        self._runner = web.AppRunner(self._app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host=self._host, port=self._port)
        await site.start()
        log.info("healthz.started", host=self._host, port=self._port)

    async def stop(self) -> None:
        """Shut down the /healthz HTTP server gracefully."""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            log.info("healthz.stopped")
