import discord

_BAR_WIDTH = 18


def format_duration(seconds: float | None) -> str:
    """Da formato m:ss o h:mm:ss a una duración, o --:-- si no se conoce."""
    if seconds is None:
        return "--:--"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def progress_bar(elapsed: float, total: float | None) -> str:
    """Dibuja una barra de progreso de texto, o cadena vacía si la duración es desconocida."""
    if not total:
        return ""
    position = min(_BAR_WIDTH - 1, int(max(elapsed, 0) / total * _BAR_WIDTH))
    return "▬" * position + "🔘" + "▬" * (_BAR_WIDTH - 1 - position)


def truncate(text: str, limit: int) -> str:
    """Recorta un texto largo agregando puntos suspensivos."""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def safe(text: str, limit: int = 70) -> str:
    """Prepara un texto externo para mostrarlo: lo recorta y neutraliza el formato de Discord."""
    return discord.utils.escape_markdown(truncate(text, limit))
