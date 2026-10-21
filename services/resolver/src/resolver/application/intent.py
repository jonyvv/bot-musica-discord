import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import ParseResult, parse_qs, urlparse

from resolver.domain.errors import UnsupportedInputError


class InputKind(StrEnum):
    YOUTUBE_VIDEO = "youtube_video"
    YOUTUBE_PLAYLIST = "youtube_playlist"
    SPOTIFY_TRACK = "spotify_track"
    SPOTIFY_ALBUM = "spotify_album"
    SPOTIFY_PLAYLIST = "spotify_playlist"
    SEARCH = "search"


@dataclass(frozen=True, slots=True)
class Intent:
    kind: InputKind
    ref: str


_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_SHORT_HOST = "youtu.be"
_VIDEO_PATHS = ("/shorts/", "/live/", "/embed/")
_SPOTIFY_HOSTS = {"open.spotify.com"}
_SPOTIFY_URI = re.compile(r"^spotify:(track|album|playlist):([A-Za-z0-9]+)$")
_SPOTIFY_PATH = re.compile(r"^/(?:intl-[a-z-]+/)?(track|album|playlist)/([A-Za-z0-9]+)")
_SPOTIFY_KINDS = {
    "track": InputKind.SPOTIFY_TRACK,
    "album": InputKind.SPOTIFY_ALBUM,
    "playlist": InputKind.SPOTIFY_PLAYLIST,
}
_UNSUPPORTED = "Solo puedo reproducir links de YouTube y Spotify, o buscar una canción por nombre."


def classify(text: str) -> Intent:
    """Determina qué tipo de entrada es el texto y qué referencia hay que resolver."""
    text = text.strip()
    if not text:
        raise UnsupportedInputError("Escribí una URL o el nombre de una canción.")
    if match := _SPOTIFY_URI.match(text):
        return Intent(_SPOTIFY_KINDS[match[1]], match[2])
    if not text.lower().startswith(("http://", "https://")):
        return Intent(InputKind.SEARCH, text)
    url = urlparse(text)
    host = (url.hostname or "").lower()
    if host in _SPOTIFY_HOSTS:
        return _classify_spotify(url)
    if host in _YOUTUBE_HOSTS or host == _SHORT_HOST:
        return _classify_youtube(url, host, text)
    raise UnsupportedInputError(_UNSUPPORTED)


def _classify_spotify(url: ParseResult) -> Intent:
    """Clasifica un link de open.spotify.com como track, álbum o playlist."""
    if match := _SPOTIFY_PATH.match(url.path):
        return Intent(_SPOTIFY_KINDS[match[1]], match[2])
    raise UnsupportedInputError("Ese link de Spotify no es de una canción, álbum o playlist.")


def _classify_youtube(url: ParseResult, host: str, original: str) -> Intent:
    """Clasifica un link de YouTube; un video dentro de una playlist cuenta solo como video."""
    params = parse_qs(url.query)
    if url.path.rstrip("/") == "/playlist" and params.get("list"):
        return Intent(
            InputKind.YOUTUBE_PLAYLIST,
            f"https://www.youtube.com/playlist?list={params['list'][0]}",
        )
    is_short_link = host == _SHORT_HOST and bool(url.path.strip("/"))
    if is_short_link or "v" in params or url.path.startswith(_VIDEO_PATHS):
        return Intent(InputKind.YOUTUBE_VIDEO, original)
    raise UnsupportedInputError(_UNSUPPORTED)
