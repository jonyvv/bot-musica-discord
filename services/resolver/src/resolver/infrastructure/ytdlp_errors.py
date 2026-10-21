from resolver.domain.errors import (
    BotDetectedError,
    ResolverError,
    TrackUnavailableError,
    UnsupportedInputError,
    UpstreamError,
)

_BOT_MARKERS = ("not a bot",)
_UNAVAILABLE_MARKERS = (
    "video unavailable",
    "is unavailable",
    "private video",
    "this video is not available",
    "members-only",
    "join this channel",
    "blocked it",
    "age-restricted",
    "confirm your age",
    "has been removed",
    "copyright",
    "premiere",
)
_MAX_DETAIL = 200


def translate_error(message: str) -> ResolverError:
    """Convierte el mensaje de error de yt-dlp en un error de dominio con texto para el usuario."""
    lowered = message.lower()
    if any(marker in lowered for marker in _BOT_MARKERS):
        return BotDetectedError(
            "YouTube bloqueó la consulta pensando que soy un bot. "
            "Hay que renovar las cookies o cambiar de red."
        )
    if "unsupported url" in lowered:
        return UnsupportedInputError("Ese link no es compatible.")
    if any(marker in lowered for marker in _UNAVAILABLE_MARKERS):
        return TrackUnavailableError(
            "Ese video no está disponible (privado, restringido o borrado)."
        )
    return UpstreamError(f"Error al consultar YouTube: {message[:_MAX_DETAIL]}")
