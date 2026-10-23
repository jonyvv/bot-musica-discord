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
_VIDEO_SEGMENTS = {"shorts", "live", "embed"}
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_PLAYLIST_ID = re.compile(r"^[A-Za-z0-9_-]{10,64}$")
_SPOTIFY_HOSTS = {"open.spotify.com"}
_SPOTIFY_URI = re.compile(r"^spotify:(track|album|playlist):([A-Za-z0-9]{1,64})$")
_SPOTIFY_PATH = re.compile(r"^/(?:intl-[a-z-]+/)?(track|album|playlist)/([A-Za-z0-9]{1,64})/?$")
_SPOTIFY_KINDS = {
    "track": InputKind.SPOTIFY_TRACK,
    "album": InputKind.SPOTIFY_ALBUM,
    "playlist": InputKind.SPOTIFY_PLAYLIST,
}
_VIDEO_URL = "https://www.youtube.com/watch?v={}"
_PLAYLIST_URL = "https://www.youtube.com/playlist?list={}"
_UNSUPPORTED = "Solo puedo reproducir links de YouTube y Spotify, o buscar una canción por nombre."


def classify(text: str) -> Intent:
    """Determina qué tipo de entrada es el texto y devuelve una referencia reconstruida y segura."""
    text = text.strip()
    if not text:
        raise UnsupportedInputError("Escribí una URL o el nombre de una canción.")
    if match := _SPOTIFY_URI.match(text):
        return Intent(_SPOTIFY_KINDS[match[1]], match[2])
    if not text.lower().startswith(("http://", "https://")):
        return Intent(InputKind.SEARCH, text)
    url = _parse(text)
    host = (url.hostname or "").lower()
    if host in _SPOTIFY_HOSTS:
        return _classify_spotify(url)
    if host in _YOUTUBE_HOSTS or host == _SHORT_HOST:
        return _classify_youtube(url, host)
    raise UnsupportedInputError(_UNSUPPORTED)


def _parse(text: str) -> ParseResult:
    """Interpreta la URL y rechaza las que traen usuario, contraseña, puerto o formato inválido."""
    try:
        url = urlparse(text)
        has_authority = bool(url.username or url.password or url.port)
    except ValueError as exc:
        raise UnsupportedInputError(_UNSUPPORTED) from exc
    if has_authority:
        raise UnsupportedInputError(_UNSUPPORTED)
    return url


def ensure_youtube_video(url: str) -> str:
    """Exige un video de YouTube y devuelve su URL canónica, nunca el texto recibido."""
    intent = classify(url)
    if intent.kind is not InputKind.YOUTUBE_VIDEO:
        raise UnsupportedInputError("Solo puedo reproducir videos de YouTube.")
    return intent.ref


def _classify_spotify(url: ParseResult) -> Intent:
    """Clasifica un link de open.spotify.com como track, álbum o playlist."""
    if match := _SPOTIFY_PATH.match(url.path):
        return Intent(_SPOTIFY_KINDS[match[1]], match[2])
    raise UnsupportedInputError("Ese link de Spotify no es de una canción, álbum o playlist.")


def _classify_youtube(url: ParseResult, host: str) -> Intent:
    """Clasifica un link de YouTube y lo reconstruye a partir de su ID, sin reutilizar el texto."""
    params = parse_qs(url.query)
    segments = [part for part in url.path.split("/") if part]
    if host == _SHORT_HOST:
        video_id = segments[0] if len(segments) == 1 else ""
    elif segments == ["watch"]:
        video_id = (params.get("v") or [""])[0]
    elif len(segments) == 2 and segments[0] in _VIDEO_SEGMENTS:
        video_id = segments[1]
    elif segments == ["playlist"]:
        return _youtube_playlist((params.get("list") or [""])[0])
    else:
        raise UnsupportedInputError(_UNSUPPORTED)
    if not _VIDEO_ID.match(video_id):
        raise UnsupportedInputError(_UNSUPPORTED)
    return Intent(InputKind.YOUTUBE_VIDEO, _VIDEO_URL.format(video_id))


def _youtube_playlist(playlist_id: str) -> Intent:
    """Arma la referencia de una playlist de YouTube a partir de su ID validado."""
    if not _PLAYLIST_ID.match(playlist_id):
        raise UnsupportedInputError(_UNSUPPORTED)
    return Intent(InputKind.YOUTUBE_PLAYLIST, _PLAYLIST_URL.format(playlist_id))
