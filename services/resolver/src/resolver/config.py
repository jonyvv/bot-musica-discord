from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    max_playlist_size: int = 500
    ytdlp_js_runtime: str = "deno"
    ytdlp_player_client: str = ""
    ytdlp_force_ipv4: bool = True
    youtube_cookies_file: str = ""
    resolver_host: str = "127.0.0.1"
    resolver_port: int = 8080
    log_level: str = "INFO"
