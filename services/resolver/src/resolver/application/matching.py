from collections.abc import Sequence

from resolver.domain.models import Track

DURATION_TOLERANCE_SECONDS = 15
SAME_DURATION_SECONDS = 5
_UNWANTED_FLAVOURS = (
    "live",
    "cover",
    "remix",
    "karaoke",
    "instrumental",
    "8d",
    "nightcore",
    "slowed",
    "sped up",
    "reverb",
    "loop",
    "1 hour",
    "parodia",
    "parody",
    "reaction",
    "reacción",
    "tutorial",
    "coreograf",
    "zumba",
    "extended",
    "mashup",
)
_CHANNEL_SUFFIXES = (" - topic", " vevo", " official")


def pick_best(
    candidates: Sequence[Track], expected_seconds: int | None, query: str
) -> Track | None:
    """Elige el mejor candidato; a igual calidad manda el orden de relevancia de la búsqueda."""
    wanted = query.lower()
    scored = []
    for position, track in enumerate(candidates):
        gap = _duration_gap(track, expected_seconds)
        if track.is_live or gap is None or gap > DURATION_TOLERANCE_SECONDS:
            continue
        key = (
            _flavour_penalty(track.title, wanted),
            0 if _channel_matches(track, wanted) else 1,
            0 if gap <= SAME_DURATION_SECONDS else gap,
            position,
        )
        scored.append((key, track))
    return min(scored, key=lambda item: item[0])[1] if scored else None


def _duration_gap(track: Track, expected_seconds: int | None) -> int | None:
    """Calcula la diferencia de duración, o None si el candidato no es comparable."""
    if expected_seconds is None:
        return 0
    if track.duration_seconds is None:
        return None
    return abs(track.duration_seconds - expected_seconds)


def _flavour_penalty(title: str, wanted: str) -> int:
    """Cuenta las marcas de versión alternativa del título que el usuario no pidió."""
    lowered = title.lower()
    return sum(1 for word in _UNWANTED_FLAVOURS if word in lowered and word not in wanted)


def _channel_matches(track: Track, wanted: str) -> bool:
    """Indica si el canal que subió el video es el artista pedido, señal de versión oficial."""
    channel = (track.artist or "").lower().strip()
    for suffix in _CHANNEL_SUFFIXES:
        channel = channel.removesuffix(suffix)
    return len(channel) > 2 and channel in wanted
