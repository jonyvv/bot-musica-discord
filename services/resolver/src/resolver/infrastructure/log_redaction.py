import logging
import re

_MASK = "***"
_RULES = (
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), rf"\1{_MASK}"),
    (
        re.compile(r"(?i)([?&;](?:sig|signature|lsig|key|token|ip|ipbits|expire|c)=)[^&;\s'\"]+"),
        rf"\1{_MASK}",
    ),
    (re.compile(r"(?i)((?:set-)?cookie:\s*)[^\r\n]+"), rf"\1{_MASK}"),
    (re.compile(r"[A-Za-z0-9_-]{23,28}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,}"), _MASK),
)
_TOKEN = re.compile(r"[^\s'\"]+")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_LINE_BREAKS = re.compile(r"[\r\n  ]+")
_MAX_LENGTH = 4000


def redact(text: str) -> str:
    """Oculta secretos y neutraliza saltos de línea y control, para que nadie falsifique el log."""
    text = _LINE_BREAKS.sub(" ", _CONTROL.sub("", text[:_MAX_LENGTH]))
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return _TOKEN.sub(_hide_cookie_path, text)


def _hide_cookie_path(match: re.Match[str]) -> str:
    """Reemplaza por un aviso genérico las rutas que parecen un archivo de cookies."""
    token = match.group(0)
    lowered = token.lower()
    return "<archivo de cookies>" if "cookie" in lowered and ".txt" in lowered else token


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        """Reemplaza el mensaje del registro por su versión sin datos sensibles."""
        record.msg = redact(record.getMessage())
        record.args = None
        return True


def install_redaction() -> None:
    """Aplica el filtro de redacción a todos los handlers del logger raíz."""
    for handler in logging.getLogger().handlers:
        handler.addFilter(RedactingFilter())
