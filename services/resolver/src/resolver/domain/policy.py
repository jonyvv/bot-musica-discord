def exceeds_limits(duration_seconds: int | None, is_live: bool, max_seconds: int) -> bool:
    """Indica si es una transmisión en vivo o dura más que el máximo (0 = sin tope)."""
    too_long = max_seconds > 0 and duration_seconds is not None and duration_seconds > max_seconds
    return is_live or too_long
