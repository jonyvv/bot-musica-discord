import pytest
from pydantic import ValidationError

from bot.config import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("DISCORD_TOKEN", "DISCORD_GUILD_ID", "IDLE_TIMEOUT", "DEFAULT_VOLUME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir("/")


def test_token_is_required():
    with pytest.raises(ValidationError):
        Settings()


def test_empty_token_is_rejected(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "")

    with pytest.raises(ValidationError):
        Settings()


def test_token_never_appears_in_repr_or_str(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "super-secret-value")

    settings = Settings()

    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings)
    assert settings.discord_token.get_secret_value() == "super-secret-value"


def test_empty_optional_variables_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "t")
    monkeypatch.setenv("DISCORD_GUILD_ID", "")

    settings = Settings()

    assert settings.discord_guild_id is None
    assert settings.idle_timeout == 300


def test_volume_is_bounded(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "t")
    monkeypatch.setenv("DEFAULT_VOLUME", "200")

    with pytest.raises(ValidationError):
        Settings()
