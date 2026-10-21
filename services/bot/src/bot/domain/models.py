from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class Source(StrEnum):
    YOUTUBE = "youtube"
    SPOTIFY = "spotify"


class CollectionKind(StrEnum):
    TRACK = "track"
    PLAYLIST = "playlist"
    ALBUM = "album"
    SEARCH = "search"


class LoopMode(StrEnum):
    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"


@dataclass(frozen=True, slots=True)
class Track:
    title: str
    artist: str | None
    duration_seconds: int | None
    source: Source
    webpage_url: str | None = None
    search_query: str | None = None
    thumbnail_url: str | None = None
    is_live: bool = False
    requester_id: int | None = None


@dataclass(frozen=True, slots=True)
class Resolution:
    kind: CollectionKind
    title: str | None
    tracks: tuple[Track, ...]
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class StreamInfo:
    url: str
    headers: Mapping[str, str]
    expires_at: int | None
    webpage_url: str
