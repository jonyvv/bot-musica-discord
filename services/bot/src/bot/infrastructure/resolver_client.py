from dataclasses import asdict
from typing import Any

import httpx

from bot.domain.errors import ResolverError, ResolverUnavailableError
from bot.domain.models import CollectionKind, Resolution, Source, StreamInfo, Track
from bot.domain.text import clean_text, safe_url

_GENERIC_ERROR = "El servicio de música respondió con un error."


class HttpTrackResolver:
    def __init__(self, client: httpx.AsyncClient):
        """Cliente HTTP del microservicio de resolución; `client` ya trae la URL base."""
        self._client = client

    async def resolve(self, query: str) -> Resolution:
        """Convierte un link o texto de búsqueda en canciones."""
        data = await self._post("/v1/resolve", {"query": query})
        return Resolution(
            kind=CollectionKind(data["kind"]),
            title=data["title"],
            tracks=tuple(_to_track(item) for item in data["tracks"]),
            truncated=data["truncated"],
        )

    async def stream(self, track: Track) -> StreamInfo:
        """Obtiene el audio reproducible de una canción."""
        payload = {key: value for key, value in asdict(track).items() if key != "requester_id"}
        data = await self._post("/v1/stream", payload)
        return StreamInfo(
            url=data["url"],
            headers=data["headers"],
            expires_at=data["expires_at"],
            webpage_url=data["webpage_url"],
        )

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """Envía el pedido y traduce los fallos de red o de servicio a errores del dominio."""
        try:
            response = await self._client.post(path, json=body)
        except httpx.TimeoutException as exc:
            raise ResolverUnavailableError("El servicio de música tardó demasiado.") from exc
        except httpx.HTTPError as exc:
            raise ResolverUnavailableError(
                "No puedo comunicarme con el servicio de música."
            ) from exc
        if response.is_success:
            return response.json()
        raise _error_from(response)


def _to_track(item: dict[str, Any]) -> Track:
    """Convierte un elemento de la respuesta en una canción del dominio."""
    duration = item.get("duration_seconds")
    return Track(
        title=clean_text(item["title"]) or "Sin título",
        artist=clean_text(item.get("artist"), 100),
        duration_seconds=duration if isinstance(duration, int) and duration >= 0 else None,
        source=Source(item["source"]),
        webpage_url=safe_url(item.get("webpage_url")),
        search_query=clean_text(item.get("search_query"), 300),
        thumbnail_url=safe_url(item.get("thumbnail_url")),
        is_live=bool(item.get("is_live", False)),
    )


def _error_from(response: httpx.Response) -> ResolverError:
    """Arma el error del dominio a partir del código y mensaje que devuelve el servicio."""
    try:
        body = response.json()
        return ResolverError(str(body["message"]), str(body["code"]))
    except (ValueError, KeyError, TypeError):
        return ResolverError(_GENERIC_ERROR)
