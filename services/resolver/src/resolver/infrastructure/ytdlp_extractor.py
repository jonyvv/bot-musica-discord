import asyncio
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from resolver.domain.errors import TrackNotFoundError, TrackUnavailableError
from resolver.domain.models import CollectionKind, Resolution, Source, StreamInfo, Track
from resolver.infrastructure.ytdlp_errors import translate_error

logger = logging.getLogger(__name__)

AUDIO_FORMAT = "bestaudio[abr<=80]/bestaudio/best"
_HIDDEN_TITLES = {"[Private video]", "[Deleted video]"}
_WATCH_URL = "https://www.youtube.com/watch?v={}"


class _SilentLogger:
    def debug(self, message: str) -> None:
        """Descarta los mensajes de depuración de yt-dlp."""

    def warning(self, message: str) -> None:
        """Descarta las advertencias de yt-dlp."""

    def error(self, message: str) -> None:
        """Descarta los errores de yt-dlp, que ya llegan como excepción."""


@dataclass(frozen=True, slots=True)
class YtDlpOptions:
    js_runtime: str = "deno"
    player_client: str = ""
    force_ipv4: bool = True
    cookies_file: str = ""


class YtDlpExtractor:
    def __init__(self, options: YtDlpOptions):
        """Adaptador de yt-dlp que ejecuta las extracciones bloqueantes fuera del event loop."""
        self._options = options
        self._warned_cookies = False

    async def video(self, url: str) -> Track:
        """Obtiene los metadatos de un video."""
        info = await self._extract(url)
        return _to_track(info)

    async def playlist(self, url: str, limit: int) -> Resolution:
        """Obtiene hasta `limit` elementos de una playlist y avisa si había más."""
        info = await self._extract(
            url, noplaylist=False, extract_flat="in_playlist", playlistend=limit + 1
        )
        tracks = _entries_to_tracks(info)
        return Resolution(
            kind=CollectionKind.PLAYLIST,
            title=info.get("title"),
            tracks=tuple(tracks[:limit]),
            truncated=len(tracks) > limit,
        )

    async def search(self, query: str, count: int) -> list[Track]:
        """Busca candidatos en YouTube por texto."""
        info = await self._extract(f"ytsearch{count}:{query}", extract_flat="in_playlist")
        return _entries_to_tracks(info)

    async def stream(self, url: str) -> StreamInfo:
        """Obtiene la URL de audio reproducible de un video, con los headers que exige."""
        info = await self._extract(url, format=AUDIO_FORMAT)
        stream_url = info.get("url")
        if not stream_url:
            raise TrackUnavailableError("No encontré un formato de audio reproducible.")
        return StreamInfo(
            url=stream_url,
            headers=dict(info.get("http_headers") or {}),
            expires_at=_expiry(stream_url),
            webpage_url=info.get("webpage_url") or url,
        )

    def _params(self, overrides: Mapping[str, Any]) -> dict[str, Any]:
        """Arma los parámetros de yt-dlp a partir de la configuración y los ajustes puntuales."""
        params: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "logger": _SilentLogger(),
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 20,
            "js_runtimes": {self._options.js_runtime: {}},
        }
        if self._options.force_ipv4:
            params["source_address"] = "0.0.0.0"
        if cookies := self._cookies_file():
            params["cookiefile"] = cookies
        if clients := [c.strip() for c in self._options.player_client.split(",") if c.strip()]:
            params["extractor_args"] = {"youtube": {"player_client": clients}}
        return {**params, **overrides}

    def _cookies_file(self) -> str | None:
        """Devuelve la ruta de cookies solo si el archivo existe; avisa una vez si no."""
        path = self._options.cookies_file
        if not path:
            return None
        if Path(path).is_file():
            return path
        if not self._warned_cookies:
            logger.warning("El archivo de cookies %s no existe; se ignora", path)
            self._warned_cookies = True
        return None

    def _extract_sync(self, target: str, overrides: Mapping[str, Any]) -> dict:
        """Ejecuta una extracción de yt-dlp y devuelve el resultado serializable."""
        ydl = YoutubeDL(self._params(overrides))
        try:
            info = ydl.extract_info(target, download=False)
            if info is None:
                raise TrackNotFoundError("No encontré nada para ese link.")
            if "entries" in info:
                info["entries"] = list(info["entries"] or [])
            return ydl.sanitize_info(info)
        finally:
            self._close(ydl)

    @staticmethod
    def _close(ydl: YoutubeDL) -> None:
        """Cierra yt-dlp sin que un fallo al guardar las cookies pierda el resultado ya obtenido."""
        try:
            ydl.close()
        except OSError as exc:
            logger.warning("No se pudieron guardar las cookies: %s", exc)

    async def _extract(self, target: str, **overrides: Any) -> dict:
        """Corre la extracción en un hilo y traduce los errores de yt-dlp a errores de dominio."""
        try:
            return await asyncio.to_thread(self._extract_sync, target, overrides)
        except DownloadError as exc:
            logger.warning("yt-dlp fallo para %s: %s", target, exc)
            raise translate_error(str(exc)) from exc


def _as_int(value: Any) -> int | None:
    """Convierte un valor numérico de yt-dlp a entero, o None si no existe."""
    return int(value) if isinstance(value, int | float) else None


def _thumbnail(entry: Mapping[str, Any]) -> str | None:
    """Obtiene la miniatura de mayor resolución disponible de una entrada."""
    if entry.get("thumbnail"):
        return entry["thumbnail"]
    thumbnails = entry.get("thumbnails") or []
    return thumbnails[-1].get("url") if thumbnails else None


def _to_track(entry: Mapping[str, Any]) -> Track:
    """Convierte una entrada de yt-dlp en una canción del dominio."""
    url = entry.get("webpage_url") or entry.get("url")
    if not url and entry.get("id"):
        url = _WATCH_URL.format(entry["id"])
    return Track(
        title=entry.get("title") or "Sin título",
        artist=entry.get("artist") or entry.get("uploader") or entry.get("channel"),
        duration_seconds=_as_int(entry.get("duration")),
        source=Source.YOUTUBE,
        webpage_url=url,
        thumbnail_url=_thumbnail(entry),
        is_live=bool(entry.get("is_live")) or entry.get("live_status") == "is_live",
    )


def _entries_to_tracks(info: Mapping[str, Any]) -> list[Track]:
    """Convierte las entradas de una playlist o búsqueda, descartando las no disponibles."""
    entries = info.get("entries") or []
    visible = [e for e in entries if e and e.get("title") not in _HIDDEN_TITLES]
    return [track for track in map(_to_track, visible) if track.webpage_url]


def _expiry(stream_url: str) -> int | None:
    """Lee el instante de vencimiento que YouTube incluye en la URL de stream."""
    values = parse_qs(urlparse(stream_url).query).get("expire")
    return int(values[0]) if values and values[0].isdigit() else None
