from collections.abc import Mapping

RECONNECT = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
PROTOCOLS = "-protocol_whitelist http,https,tcp,tls,crypto"
OUTPUT_OPTIONS = "-vn"
_BASE = f"{PROTOCOLS} {RECONNECT}"


def before_options(headers: Mapping[str, str]) -> str:
    """Arma las opciones de entrada de FFmpeg: solo red, reconexión y headers HTTP de la fuente."""
    if not headers:
        return _BASE
    joined = "".join(f"{_clean(name)}: {_clean(value)}\r\n" for name, value in headers.items())
    return f'{_BASE} -headers "{joined}"'


def is_remote_url(url: str) -> bool:
    """Indica si la URL es http(s) sin espacios ni saltos de línea, la única entrada admitida."""
    return url.startswith(("https://", "http://")) and url.isprintable() and " " not in url


def _clean(text: str) -> str:
    """Quita comillas, barras y saltos de línea que romperían el argumento de FFmpeg."""
    return text.replace('"', "").replace("\\", "").replace("\r", "").replace("\n", "")
