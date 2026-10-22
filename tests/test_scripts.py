import os
import stat

import gen_api_key
import pytest
import store_secret

from resolver.presentation.auth import hash_api_key

VALID_TOKEN = "A" * 24 + "." + "B" * 6 + "." + "C" * 30


class MemoryStore:
    def __init__(self, fail=False):
        self.items = {}
        self.fail = fail

    def __call__(self, name, value):
        if self.fail:
            raise RuntimeError("sin almacén")
        self.items[name] = value


def test_set_env_value_replaces_existing_and_keeps_other_lines(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\nRESOLVER_API_KEY_SHA256=viejo\nB=2\n")

    gen_api_key.set_env_value(env, "RESOLVER_API_KEY_SHA256", "nuevo")

    assert env.read_text().splitlines() == ["A=1", "RESOLVER_API_KEY_SHA256=nuevo", "B=2"]


def test_set_env_value_appends_when_missing_and_creates_the_file(tmp_path):
    env = tmp_path / ".env"

    gen_api_key.set_env_value(env, "X", "1")
    gen_api_key.set_env_value(env, "X", "1")

    assert env.read_text().splitlines() == ["X=1"]


def test_generated_key_goes_to_the_store_and_only_its_hash_to_the_env_file(tmp_path):
    env = tmp_path / ".env"
    vault = MemoryStore()

    message = gen_api_key.generate(env, store=vault, make_key=lambda n: "k" * 43)

    key = vault.items["RESOLVER_API_KEY"]
    text = env.read_text()
    assert f"RESOLVER_API_KEY_SHA256={hash_api_key(key)}" in text
    assert key not in text
    assert key not in message


def test_generation_never_overwrites_an_existing_key_without_force(tmp_path):
    env = tmp_path / ".env"
    vault = MemoryStore()
    gen_api_key.generate(env, store=vault)
    before = env.read_text()

    message = gen_api_key.generate(env, store=vault)

    assert env.read_text() == before
    assert "--force" in message
    gen_api_key.generate(env, store=vault, force=True)
    assert env.read_text() != before


def test_without_a_secret_store_the_key_falls_back_to_the_env_file_with_a_warning(tmp_path):
    env = tmp_path / ".env"

    message = gen_api_key.generate(env, store=MemoryStore(fail=True), make_key=lambda n: "z" * 43)

    assert "RESOLVER_API_KEY=" + "z" * 43 in env.read_text()
    assert "Protegé" in message


def test_secret_files_for_docker_are_created_private(tmp_path):
    env = tmp_path / ".env"
    secrets = tmp_path / "secrets"

    gen_api_key.generate(env, secrets_dir=secrets, make_key=lambda n: "d" * 43)

    assert (secrets / "resolver_api_key").read_text() == "d" * 43
    assert (secrets / "resolver_api_key_sha256").read_text() == hash_api_key("d" * 43)
    if os.name == "posix":
        assert stat.S_IMODE((secrets / "resolver_api_key").stat().st_mode) == 0o600


def test_the_generated_key_is_long_and_random():
    first = gen_api_key.secrets.token_urlsafe(32)
    second = gen_api_key.secrets.token_urlsafe(32)

    assert len(first) >= 43
    assert first != second


def test_a_discord_token_goes_to_the_store(tmp_path):
    vault = MemoryStore()

    message = store_secret.store("DISCORD_TOKEN", f" {VALID_TOKEN}\n", save=vault)

    assert vault.items == {"DISCORD_TOKEN": VALID_TOKEN}
    assert VALID_TOKEN not in message


@pytest.mark.parametrize("value", ["", "   ", "no-es-un-token", "a.b.c", "x" * 100])
def test_invalid_tokens_are_refused(value):
    vault = MemoryStore()

    with pytest.raises(SystemExit):
        store_secret.store("DISCORD_TOKEN", value, save=vault)

    assert vault.items == {}


def test_a_secret_can_be_written_to_a_private_file(tmp_path):
    target = tmp_path / "secrets" / "discord_token"

    store_secret.store("DISCORD_TOKEN", VALID_TOKEN, file=target, save=MemoryStore(fail=True))

    assert target.read_text() == VALID_TOKEN
    if os.name == "posix":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
