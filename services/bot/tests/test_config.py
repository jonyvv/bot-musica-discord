import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import KeyringError
from pydantic import SecretStr, ValidationError

from bot import main
from bot.config import Settings
from bot.infrastructure import secret_store

ENV_NAMES = (
    "DISCORD_TOKEN",
    "DISCORD_GUILD_ID",
    "ALLOWED_GUILD_IDS",
    "RESOLVER_API_KEY",
    "IDLE_TIMEOUT",
    "DEFAULT_VOLUME",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self):
        self.items = {}

    def get_password(self, service, username):
        return self.items.get((service, username))

    def set_password(self, service, username, password):
        self.items[(service, username)] = password

    def delete_password(self, service, username):
        self.items.pop((service, username), None)


class BrokenKeyring(MemoryKeyring):
    def get_password(self, service, username):
        raise KeyringError("sin almacén")


@pytest.fixture
def vault():
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


def test_settings_defaults_do_not_require_a_token():
    assert Settings().discord_token.get_secret_value() == ""


def test_token_never_appears_in_repr_or_str(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "super-secret-value")

    settings = Settings()

    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings)
    assert settings.discord_token.get_secret_value() == "super-secret-value"


def test_resolver_key_never_appears_in_repr(monkeypatch):
    monkeypatch.setenv("RESOLVER_API_KEY", "clave-muy-secreta")

    assert "clave-muy-secreta" not in repr(Settings())


def test_empty_optional_variables_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("DISCORD_GUILD_ID", "")

    settings = Settings()

    assert settings.discord_guild_id is None
    assert settings.idle_timeout == 300


def test_volume_is_bounded(monkeypatch):
    monkeypatch.setenv("DEFAULT_VOLUME", "200")

    with pytest.raises(ValidationError):
        Settings()


def test_secrets_are_read_from_a_docker_secrets_directory(tmp_path):
    secrets = tmp_path / "run-secrets"
    secrets.mkdir()
    (secrets / "discord_token").write_text("token-desde-archivo\n")
    (secrets / "resolver_api_key").write_text("clave-desde-archivo\n")

    settings = Settings(_secrets_dir=secrets)

    assert settings.discord_token.get_secret_value() == "token-desde-archivo"
    assert settings.resolver_api_key.get_secret_value() == "clave-desde-archivo"


def test_environment_wins_over_secret_files(monkeypatch, tmp_path):
    (tmp_path / "discord_token").write_text("del-archivo")
    monkeypatch.setenv("DISCORD_TOKEN", "del-entorno")

    assert Settings(_secrets_dir=tmp_path).discord_token.get_secret_value() == "del-entorno"


@pytest.mark.parametrize("value", ["abc", "123,abc", "12 34", "-5", "1.5"])
def test_allowed_guild_ids_must_be_numeric(monkeypatch, value):
    monkeypatch.setenv("ALLOWED_GUILD_IDS", value)

    with pytest.raises(ValidationError):
        Settings()


def test_allowed_guilds_come_from_the_explicit_list(monkeypatch):
    monkeypatch.setenv("ALLOWED_GUILD_IDS", "111, 222")
    monkeypatch.setenv("DISCORD_GUILD_ID", "999")

    assert Settings().allowed_guilds == frozenset({111, 222})


def test_allowed_guilds_fall_back_to_the_main_guild(monkeypatch):
    monkeypatch.setenv("DISCORD_GUILD_ID", "999")

    assert Settings().allowed_guilds == frozenset({999})


def test_allowed_guilds_are_empty_when_nothing_is_configured():
    assert Settings().allowed_guilds == frozenset()


def test_missing_token_stops_startup_with_instructions(monkeypatch):
    monkeypatch.setattr(main, "load_secret", lambda name: None)

    with pytest.raises(SystemExit) as caught:
        main.load_settings()

    assert str(caught.value) == main.MISSING_TOKEN_HINT


def test_token_is_taken_from_the_secret_store_when_not_in_the_environment(monkeypatch):
    stored = {"DISCORD_TOKEN": "token-del-almacen", "RESOLVER_API_KEY": "clave-del-almacen"}
    monkeypatch.setattr(main, "load_secret", stored.get)

    settings = main.load_settings()

    assert settings.discord_token.get_secret_value() == "token-del-almacen"
    assert settings.resolver_api_key.get_secret_value() == "clave-del-almacen"
    assert "token-del-almacen" not in repr(settings)


def test_environment_takes_precedence_over_the_secret_store(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "del-entorno")
    monkeypatch.setattr(main, "load_secret", lambda name: "del-almacen")

    assert main.load_settings().discord_token.get_secret_value() == "del-entorno"


def test_resolver_header_carries_the_key_only_when_configured():
    with_key = Settings(resolver_api_key=SecretStr("k"))

    assert main.resolver_headers(with_key) == {"Authorization": "Bearer k"}
    assert main.resolver_headers(Settings()) == {}


def test_secret_store_round_trip(vault):
    secret_store.save_secret("DISCORD_TOKEN", "valor")

    assert secret_store.load_secret("DISCORD_TOKEN") == "valor"
    assert secret_store.load_secret("OTRO") is None


def test_secret_store_without_a_backend_returns_nothing():
    previous = keyring.get_keyring()
    keyring.set_keyring(BrokenKeyring())
    try:
        assert secret_store.load_secret("DISCORD_TOKEN") is None
    finally:
        keyring.set_keyring(previous)


def test_tools_can_load_settings_without_a_discord_token(monkeypatch):
    monkeypatch.setattr(main, "load_secret", {"RESOLVER_API_KEY": "clave-del-almacen"}.get)

    settings = main.load_settings(require_token=False)

    assert settings.resolver_api_key.get_secret_value() == "clave-del-almacen"
    assert settings.discord_token.get_secret_value() == ""
