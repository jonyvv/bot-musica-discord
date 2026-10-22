from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DOCKER_SECRETS = Path("/run/secrets")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
        secrets_dir=_DOCKER_SECRETS if _DOCKER_SECRETS.is_dir() else None,
    )

    max_playlist_size: int = Field(default=500, ge=1)
    max_track_seconds: int = Field(default=10_800, ge=0)
    ytdlp_js_runtime: str = "deno"
    ytdlp_player_client: str = "tv_simply,web_embedded"
    ytdlp_force_ipv4: bool = True
    youtube_cookies_file: str = ""
    ytdlp_auto_update: bool = False
    ytdlp_update_interval_hours: int = 24
    ytdlp_max_concurrent: int = Field(default=3, ge=1)
    ytdlp_min_interval_seconds: float = Field(default=0.3, ge=0)
    youtube_block_threshold: int = Field(default=3, ge=1)
    youtube_block_cooldown_seconds: int = Field(default=600, ge=1)
    cache_ttl_seconds: int = Field(default=600, ge=0)
    resolver_host: str = "127.0.0.1"
    resolver_port: int = 8080
    resolver_api_key_sha256: str = ""
    rate_limit_per_minute: int = Field(default=120, ge=0)
    max_body_bytes: int = Field(default=65_536, ge=1024)
    max_client_concurrency: int = Field(default=16, ge=0)
    header_timeout_seconds: float = Field(default=10.0, gt=0)
    max_connections_per_client: int = Field(default=32, ge=0)
    body_timeout_seconds: float = Field(default=10.0, gt=0)
    auth_failure_limit: int = Field(default=5, ge=1)
    auth_failure_window_seconds: int = Field(default=300, ge=1)
    log_level: str = "INFO"

    @field_validator("resolver_api_key_sha256")
    @classmethod
    def must_be_a_sha256_digest(cls, value: str) -> str:
        """Rechaza lo que no sea un SHA-256 hexadecimal, p. ej. una clave pegada en claro."""
        if value and (len(value) != 64 or any(c not in "0123456789abcdefABCDEF" for c in value)):
            raise ValueError("debe ser el SHA-256 de la clave en hexadecimal (64 caracteres)")
        return value
