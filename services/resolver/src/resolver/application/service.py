from collections.abc import Awaitable, Callable

from resolver.application.intent import InputKind, classify
from resolver.application.matching import pick_best
from resolver.application.ports import MediaExtractor, SpotifyCatalog
from resolver.domain.errors import TrackNotFoundError
from resolver.domain.models import CollectionKind, Resolution, StreamInfo, Track

SEARCH_CANDIDATES = 5


class ResolverService:
    def __init__(self, extractor: MediaExtractor, spotify: SpotifyCatalog, max_playlist_size: int):
        """Une los adaptadores de YouTube y Spotify detrás de resolver y streamear."""
        self._extractor = extractor
        self._spotify = spotify
        self._limit = max_playlist_size
        self._handlers: dict[InputKind, Callable[[str], Awaitable[Resolution]]] = {
            InputKind.YOUTUBE_VIDEO: self._youtube_video,
            InputKind.YOUTUBE_PLAYLIST: self._youtube_playlist,
            InputKind.SPOTIFY_TRACK: self._spotify_track,
            InputKind.SPOTIFY_ALBUM: self._spotify_album,
            InputKind.SPOTIFY_PLAYLIST: self._spotify_playlist,
            InputKind.SEARCH: self._search,
        }

    async def resolve(self, text: str) -> Resolution:
        """Convierte un link o un texto de búsqueda en las canciones que representa."""
        intent = classify(text)
        return await self._handlers[intent.kind](intent.ref)

    async def stream(self, track: Track) -> StreamInfo:
        """Obtiene el audio reproducible de una canción, buscándola en YouTube si hace falta."""
        url = track.webpage_url or await self._match_on_youtube(track)
        return await self._extractor.stream(url)

    async def _match_on_youtube(self, track: Track) -> str:
        """Encuentra en YouTube el equivalente de una canción que solo tiene metadatos."""
        query = track.search_query or f"{track.artist or ''} {track.title}".strip()
        candidates = await self._extractor.search(query, SEARCH_CANDIDATES)
        best = pick_best(candidates, track.duration_seconds, query)
        if best is None or best.webpage_url is None:
            raise TrackNotFoundError(f"No encontré una versión reproducible de «{track.title}».")
        return best.webpage_url

    async def _youtube_video(self, url: str) -> Resolution:
        """Resuelve un link de video de YouTube."""
        track = await self._extractor.video(url)
        return Resolution(CollectionKind.TRACK, track.title, (track,))

    async def _youtube_playlist(self, url: str) -> Resolution:
        """Resuelve una playlist de YouTube respetando el tope configurado."""
        return await self._extractor.playlist(url, self._limit)

    async def _spotify_track(self, ref: str) -> Resolution:
        """Resuelve un track de Spotify a sus metadatos."""
        track = await self._spotify.track(ref)
        return Resolution(CollectionKind.TRACK, track.title, (track,))

    async def _spotify_album(self, ref: str) -> Resolution:
        """Resuelve un álbum de Spotify respetando el tope configurado."""
        return await self._spotify.album(ref, self._limit)

    async def _spotify_playlist(self, ref: str) -> Resolution:
        """Resuelve una playlist de Spotify respetando el tope configurado."""
        return await self._spotify.playlist(ref, self._limit)

    async def _search(self, query: str) -> Resolution:
        """Resuelve un texto libre al mejor resultado de búsqueda."""
        candidates = await self._extractor.search(query, SEARCH_CANDIDATES)
        best = pick_best(candidates, None, query)
        if best is None:
            raise TrackNotFoundError(f"No encontré resultados para «{query}».")
        return Resolution(CollectionKind.SEARCH, best.title, (best,))
