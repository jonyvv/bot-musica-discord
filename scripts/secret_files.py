import os
from pathlib import Path


def write_private(path: Path, content: str) -> None:
    """Escribe un archivo de secreto que solo puede leer su dueño (en sistemas POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)
