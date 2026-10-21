import logging
import os
import signal

import httpx
import uvicorn
from fastapi import FastAPI

from resolver.application.service import ResolverService
from resolver.config import Settings
from resolver.infrastructure.spotify_embed import SpotifyEmbedCatalog
from resolver.infrastructure.updater import YtDlpUpdater
from resolver.infrastructure.ytdlp_extractor import YtDlpExtractor, YtDlpOptions
from resolver.presentation.api import create_app

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


def build_app() -> FastAPI:
    """Compone los adaptadores con el servicio y devuelve la aplicación lista para servir."""
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    http = httpx.AsyncClient(
        timeout=20,
        follow_redirects=True,
        headers={"User-Agent": _BROWSER_UA, "Accept-Language": "en"},
    )
    extractor = YtDlpExtractor(
        YtDlpOptions(
            js_runtime=settings.ytdlp_js_runtime,
            player_client=settings.ytdlp_player_client,
            force_ipv4=settings.ytdlp_force_ipv4,
            cookies_file=settings.youtube_cookies_file,
        )
    )
    service = ResolverService(extractor, SpotifyEmbedCatalog(http), settings.max_playlist_size)
    updater = _build_updater(settings)
    return create_app(
        service, on_shutdown=http.aclose, background=updater.run_forever if updater else None
    )


def _build_updater(settings: Settings) -> YtDlpUpdater | None:
    """Crea el actualizador de yt-dlp si está habilitado; al actualizar apaga el proceso."""
    if not settings.ytdlp_auto_update:
        return None
    interval = settings.ytdlp_update_interval_hours * 3600
    return YtDlpUpdater(interval, on_updated=lambda: os.kill(os.getpid(), signal.SIGTERM))


def run() -> None:
    """Levanta el servidor HTTP con la configuración del entorno."""
    settings = Settings()
    uvicorn.run(
        "resolver.main:build_app",
        factory=True,
        host=settings.resolver_host,
        port=settings.resolver_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
