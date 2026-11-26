from pathlib import Path

import pytest

from thesnow.config import ConfigError, load_settings


def test_load_settings_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    with pytest.raises(ConfigError, match="DISCORD_TOKEN"):
        load_settings()


def test_load_settings_parses_guild_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "123")
    monkeypatch.setenv("ALLOWED_GUILD_IDS", "123, 456")
    monkeypatch.setenv("DB_PATH", "custom/data.db")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("SCHEDULE_GRACE_SECONDS", "600")

    settings = load_settings()

    assert settings.guild_id == 123
    assert settings.allowed_guild_ids == frozenset({123, 456})
    assert settings.db_path == Path("custom/data.db")
    assert settings.log_level == "DEBUG"
    assert settings.schedule_grace_seconds == 600


def test_load_settings_rejects_bad_guild_ids_and_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "not-an-int")
    with pytest.raises(ConfigError, match="GUILD_ID"):
        load_settings()

    monkeypatch.delenv("GUILD_ID")
    monkeypatch.setenv("SCHEDULE_GRACE_SECONDS", "-5")
    with pytest.raises(ConfigError, match="SCHEDULE_GRACE_SECONDS"):
        load_settings()
