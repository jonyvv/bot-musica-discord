from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DOCKER_SECRETS = Path("/run/secrets")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
        secrets_dir=_DOCKER_SECRETS if _DOCKER_SECRETS.is_dir() else None,
    )

    discord_token: SecretStr = SecretStr("")
    discord_guild_id: int | None = None
    allowed_guild_ids: str = ""
    resolver_url: str = "http://127.0.0.1:8080"
    resolver_api_key: SecretStr = SecretStr("")
    idle_timeout: int = Field(default=300, ge=0)
    empty_timeout: int = Field(default=120, ge=0)
    pause_timeout: int = Field(default=600, ge=0)
    default_volume: int = Field(default=50, ge=0, le=150)
    max_queue_size: int = Field(default=1000, ge=1)
    max_tracks_per_user: int = Field(default=200, ge=0)
    max_inflight_requests: int = Field(default=3, ge=1)
    user_commands_per_10s: int = Field(default=8, ge=1)
    guild_commands_per_10s: int = Field(default=30, ge=1)
    log_level: str = "INFO"

    @field_validator("allowed_guild_ids")
    @classmethod
    def must_be_numeric_ids(cls, value: str) -> str:
        """Verifica que la lista de servidores sea de IDs numéricos separados por comas."""
        if any(not part.strip().isdigit() for part in value.split(",") if part.strip()):
            raise ValueError("debe ser una lista de IDs numéricos separados por comas")
        return value

    @property
    def allowed_guilds(self) -> frozenset[int]:
        """Servidores donde el bot puede operar; vacío significa sin restricción."""
        listed = {int(part) for part in self.allowed_guild_ids.split(",") if part.strip()}
        if listed:
            return frozenset(listed)
        return frozenset({self.discord_guild_id}) if self.discord_guild_id else frozenset()
