import json
import re
from collections.abc import Mapping
from typing import Any

import httpx

from resolver.domain.errors import SpotifyUnavailableError, UpstreamError
from resolver.domain.models import CollectionKind, Resolution, Source, Track

_EMBED_URL = "https://open.spotify.com/embed/{kind}/{ref}"
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
_UNEXPECTED = "Spotify cambió el formato de sus páginas y no pude leer ese link."


class SpotifyEmbedCatalog:
    def __init__(self, client: httpx.AsyncClient):
        """Lee metadatos de Spotify desde sus páginas embed públicas, sin credenciales de API."""
        self._client = client

    async def track(self, ref: str) -> Track:
        """Obtiene los metadatos de un track de Spotify."""
        entity = await self._entity("track", ref)
        artists = ", ".join(a["name"] for a in entity.get("artists", []) if a.get("name"))
        return _build_track(entity.get("name", ""), artists, entity.get("duration"))

    async def album(self, ref: str, limit: int) -> Resolution:
        """Obtiene hasta `limit` tracks de un álbum de Spotify."""
        return await self._collection("album", CollectionKind.ALBUM, ref, limit)

    async def playlist(self, ref: str, limit: int) -> Resolution:
        """Obtiene hasta `limit` tracks de una playlist de Spotify."""
        return await self._collection("playlist", CollectionKind.PLAYLIST, ref, limit)

    async def _collection(
        self, kind: str, collection: CollectionKind, ref: str, limit: int
    ) -> Resolution:
        """Lee una colección de Spotify y la convierte en una resolución acotada por el tope."""
        entity = await self._entity(kind, ref)
        items = entity.get("trackList") or []
        if not items:
            raise SpotifyUnavailableError("Esa lista de Spotify está vacía o no es pública.")
        tracks = [
            _build_track(
                item.get("title", ""), _clean_artists(item.get("subtitle")), item.get("duration")
            )
            for item in items
        ]
        return Resolution(
            kind=collection,
            title=entity.get("name") or entity.get("title"),
            tracks=tuple(tracks[:limit]),
            truncated=len(tracks) > limit,
        )

    async def _entity(self, kind: str, ref: str) -> Mapping[str, Any]:
        """Descarga la página embed y extrae la entidad que Spotify incrusta en ella."""
        try:
            response = await self._client.get(_EMBED_URL.format(kind=kind, ref=ref))
        except httpx.HTTPError as exc:
            raise UpstreamError("No pude conectar con Spotify.") from exc
        if response.status_code == 404:
            raise SpotifyUnavailableError("Ese contenido de Spotify no existe o no es público.")
        if response.status_code >= 400:
            raise UpstreamError(f"Spotify respondió con un error ({response.status_code}).")
        return _parse_entity(response.text)


def _parse_entity(html: str) -> Mapping[str, Any]:
    """Extrae la entidad del JSON incrustado en la página, o falla si el formato cambió."""
    match = _NEXT_DATA.search(html)
    if not match:
        raise UpstreamError(_UNEXPECTED)
    try:
        return json.loads(match[1])["props"]["pageProps"]["state"]["data"]["entity"]
    except (KeyError, TypeError, ValueError) as exc:
        raise UpstreamError(_UNEXPECTED) from exc


def _clean_artists(subtitle: str | None) -> str:
    """Normaliza la lista de artistas, que Spotify separa con comas y espacios especiales."""
    return ", ".join(part.strip() for part in (subtitle or "").split(",") if part.strip())


def _build_track(title: str, artists: str, duration_ms: int | None) -> Track:
    """Arma una canción de Spotify, sin URL: el audio se busca en YouTube al reproducir."""
    primary = artists.split(",")[0].strip()
    query = f"{primary} - {title}" if primary else title
    return Track(
        title=title or "Sin título",
        artist=artists or None,
        duration_seconds=round(duration_ms / 1000) if duration_ms else None,
        source=Source.SPOTIFY,
        search_query=query,
    )
