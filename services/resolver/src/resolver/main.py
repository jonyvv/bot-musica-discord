import logging
import os
import signal

import httpx
import uvicorn
from fastapi import FastAPI

from resolver.application.service import ResolverService
from resolver.config import Settings
from resolver.infrastructure.log_redaction import install_redaction
from resolver.infrastructure.pacing import Pacer
from resolver.infrastructure.protection import CircuitBreaker, ProtectedExtractor
from resolver.infrastructure.spotify_embed import SpotifyEmbedCatalog
from resolver.infrastructure.updater import YtDlpUpdater
from resolver.infrastructure.ytdlp_extractor import YtDlpExtractor, YtDlpOptions
from resolver.presentation.api import create_app
from resolver.presentation.security import SecurityPolicy

logger = logging.getLogger(__name__)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
_MAX_SERVER_CONNECTIONS = 64
_KEEP_ALIVE_SECONDS = 5


def build_app() -> FastAPI:
    """Compone los adaptadores con el servicio y devuelve la aplicación lista para servir."""
    settings = Settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    install_redaction()
    if not settings.resolver_api_key_sha256:
        logger.warning("RESOLVER_API_KEY_SHA256 no está definida: la API acepta pedidos sin clave")
    http = httpx.AsyncClient(
        timeout=20,
        follow_redirects=False,
        headers={"User-Agent": _BROWSER_UA, "Accept-Language": "en"},
    )
    service = ResolverService(
        _build_extractor(settings),
        SpotifyEmbedCatalog(http),
        settings.max_playlist_size,
        settings.max_track_seconds,
    )
    updater = _build_updater(settings)
    return create_app(
        service,
        on_shutdown=http.aclose,
        background=updater.run_forever if updater else None,
        security=_build_policy(settings),
    )


def _build_extractor(settings: Settings) -> ProtectedExtractor:
    """Arma el extractor de YouTube envuelto en espaciado, caché y cortacircuito."""
    inner = YtDlpExtractor(
        YtDlpOptions(
            js_runtime=settings.ytdlp_js_runtime,
            player_client=settings.ytdlp_player_client,
            force_ipv4=settings.ytdlp_force_ipv4,
            cookies_file=settings.youtube_cookies_file,
            max_track_seconds=settings.max_track_seconds,
        )
    )
    return ProtectedExtractor(
        inner,
        Pacer(settings.ytdlp_max_concurrent, settings.ytdlp_min_interval_seconds),
        CircuitBreaker(settings.youtube_block_threshold, settings.youtube_block_cooldown_seconds),
        ttl_seconds=settings.cache_ttl_seconds,
    )


def _build_policy(settings: Settings) -> SecurityPolicy:
    """Traduce la configuración a la política de seguridad de la API."""
    return SecurityPolicy(
        api_key_sha256=settings.resolver_api_key_sha256,
        requests_per_minute=settings.rate_limit_per_minute,
        max_body_bytes=settings.max_body_bytes,
        auth_failure_limit=settings.auth_failure_limit,
        auth_failure_window_seconds=settings.auth_failure_window_seconds,
    )


def _build_updater(settings: Settings) -> YtDlpUpdater | None:
    """Crea el actualizador de yt-dlp si está habilitado; al actualizar apaga el proceso."""
    if not settings.ytdlp_auto_update:
        return None
    interval = settings.ytdlp_update_interval_hours * 3600
    return YtDlpUpdater(interval, on_updated=lambda: os.kill(os.getpid(), signal.SIGTERM))


def run() -> None:
    """Levanta el servidor HTTP con límites de conexiones concurrentes y de inactividad."""
    settings = Settings()
    uvicorn.run(
        "resolver.main:build_app",
        factory=True,
        host=settings.resolver_host,
        port=settings.resolver_port,
        log_level=settings.log_level.lower(),
        limit_concurrency=_MAX_SERVER_CONNECTIONS,
        timeout_keep_alive=_KEEP_ALIVE_SECONDS,
    )


if __name__ == "__main__":
    run()
