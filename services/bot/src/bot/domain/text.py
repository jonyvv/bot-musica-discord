import re
import unicodedata

_URL_FORBIDDEN = frozenset(" ()<>\"'`\\")
_MARKUP = re.compile(r"([\\*_~|>`\[\]()#@:<])")


def clean_text(value: str | None, limit: int = 150) -> str | None:
    """Quita caracteres de control y de dirección, las comillas invertidas y acota el largo."""
    if value is None:
        return None
    visible = "".join(" " if ch.isspace() else ch for ch in value if not _is_hidden(ch))
    cleaned = " ".join(visible.replace("`", "'").split())
    return cleaned[:limit] or None


def safe_url(value: str | None) -> str | None:
    """Acepta solo URLs https sin caracteres que permitan romper un enlace de markdown."""
    if not value or not value.startswith("https://") or any(ch in _URL_FORBIDDEN for ch in value):
        return None
    return value if value.isprintable() and len(value) <= 2048 else None


def escape_markup(text: str) -> str:
    """Escapa el formato de Discord (énfasis, enlaces, menciones y código) de un texto externo."""
    return _MARKUP.sub(r"\\\1", text)


def _is_hidden(char: str) -> bool:
    """Indica si el carácter es invisible o altera el orden del texto, salvo los espacios."""
    return not char.isspace() and unicodedata.category(char).startswith("C")
