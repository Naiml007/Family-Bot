"""Unit tests for module discovery, layering rules, and /healthz server."""

from __future__ import annotations

from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from familybot.app import discover_module_extensions
from familybot.core.config import Settings
from familybot.observability.health import HealthServer, HealthSnapshot


def test_settings_accepts_blank_optional_env_vars() -> None:
    settings = Settings(DISCORD_GUILD_ID="", SENTRY_DSN="", GIT_SHA="")  # type: ignore[arg-type]
    assert settings.DISCORD_GUILD_ID is None
    assert settings.SENTRY_DSN is None
    assert settings.GIT_SHA is None


def test_discover_module_extensions_finds_admin() -> None:
    extensions = discover_module_extensions()
    assert "familybot.modules.admin.cog" in extensions


def test_services_never_import_discord() -> None:
    modules_root = Path(__file__).resolve().parents[2] / "src" / "familybot" / "modules"
    service_files = list(modules_root.glob("*/service.py"))
    assert service_files, "Expected at least one service.py file"
    for path in service_files:
        content = path.read_text(encoding="utf-8")
        assert "import discord" not in content, f"{path} must not import discord"
        assert "from discord" not in content, f"{path} must not import discord"


async def test_healthz_endpoint_returns_200_and_503() -> None:
    healthy = True

    async def probe() -> HealthSnapshot:
        return HealthSnapshot(
            ok=healthy,
            db_ok=healthy,
            db_latency_ms=2.34 if healthy else None,
            uptime_seconds=10.5,
            version="0.1.0",
        )

    server = HealthServer(host="127.0.0.1", port=0, probe=probe)
    async with TestClient(TestServer(server.app)) as client:
        resp_ok = await client.get("/healthz")
        assert resp_ok.status == 200
        body_ok = await resp_ok.json()
        assert body_ok["status"] == "ok"
        assert body_ok["db"] == "ok"

        healthy = False
        resp_err = await client.get("/healthz")
        assert resp_err.status == 503
        body_err = await resp_err.json()
        assert body_err["status"] == "degraded"
        assert body_err["db"] == "error"
