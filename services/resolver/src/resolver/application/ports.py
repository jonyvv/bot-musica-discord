from typing import Protocol

from resolver.domain.models import Resolution, StreamInfo, Track


class MediaExtractor(Protocol):
    async def video(self, url: str) -> Track:
        """Obtiene los metadatos de un video."""
        ...

    async def playlist(self, url: str, limit: int) -> Resolution:
        """Obtiene hasta `limit` elementos de una playlist."""
        ...

    async def search(self, query: str, count: int) -> list[Track]:
        """Busca candidatos por texto."""
        ...

    async def stream(self, url: str) -> StreamInfo:
        """Obtiene la URL de audio reproducible de un video."""
        ...


class SpotifyCatalog(Protocol):
    async def track(self, ref: str) -> Track:
        """Obtiene los metadatos de un track de Spotify."""
        ...

    async def album(self, ref: str, limit: int) -> Resolution:
        """Obtiene hasta `limit` tracks de un álbum de Spotify."""
        ...

    async def playlist(self, ref: str, limit: int) -> Resolution:
        """Obtiene hasta `limit` tracks de una playlist de Spotify."""
        ...
