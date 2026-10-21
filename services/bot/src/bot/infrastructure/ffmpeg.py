from collections.abc import Mapping

RECONNECT = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
OUTPUT_OPTIONS = "-vn"


def before_options(headers: Mapping[str, str]) -> str:
    """Arma las opciones de entrada de FFmpeg: reconexión y headers HTTP de la fuente."""
    if not headers:
        return RECONNECT
    joined = "".join(f"{_clean(name)}: {_clean(value)}\r\n" for name, value in headers.items())
    return f'{RECONNECT} -headers "{joined}"'


def _clean(text: str) -> str:
    """Quita comillas, barras y saltos de línea que romperían el argumento de FFmpeg."""
    return text.replace('"', "").replace("\\", "").replace("\r", "").replace("\n", "")
