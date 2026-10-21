from collections.abc import Sequence

from resolver.domain.models import Track

DURATION_TOLERANCE_SECONDS = 15
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
)


def pick_best(
    candidates: Sequence[Track], expected_seconds: int | None, query: str
) -> Track | None:
    """Elige el mejor candidato por cercanía de duración, evitando versiones no deseadas."""
    wanted = query.lower()
    scored = []
    for position, track in enumerate(candidates):
        gap = _duration_gap(track, expected_seconds)
        if track.is_live or gap is None or gap > DURATION_TOLERANCE_SECONDS:
            continue
        scored.append((_flavour_penalty(track.title, wanted), gap, position, track))
    return min(scored, key=lambda item: item[:3])[3] if scored else None


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
