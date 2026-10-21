from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    discord_token: SecretStr = Field(min_length=1)
    discord_guild_id: int | None = None
    resolver_url: str = "http://127.0.0.1:8080"
    idle_timeout: int = Field(default=300, ge=0)
    empty_timeout: int = Field(default=120, ge=0)
    pause_timeout: int = Field(default=600, ge=0)
    default_volume: int = Field(default=50, ge=0, le=150)
    max_queue_size: int = Field(default=1000, ge=1)
    log_level: str = "INFO"
