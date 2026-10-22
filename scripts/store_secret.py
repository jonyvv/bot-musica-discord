"""Guarda un secreto pidiéndolo sin eco, para que no quede en el historial de la terminal."""

import argparse
import getpass
import re
from collections.abc import Callable
from pathlib import Path

from secret_files import write_private

from bot.infrastructure.secret_store import save_secret

DISCORD_TOKEN_SHAPE = re.compile(r"^[A-Za-z0-9_-]{23,}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,}$")


def store(
    name: str,
    value: str,
    file: Path | None = None,
    save: Callable[[str, str], None] = save_secret,
) -> str:
    """Guarda el secreto en el almacén cifrado, o en un archivo privado si se indica."""
    value = value.strip()
    if not value:
        raise SystemExit("El valor está vacío; no se guardó nada.")
    if name == "DISCORD_TOKEN" and not DISCORD_TOKEN_SHAPE.match(value):
        raise SystemExit("Eso no parece un token de Discord (formato xxx.yyy.zzz); no se guardó.")
    if file is not None:
        write_private(file, value)
        return f"{name} guardado en {file}."
    save(name, value)
    return f"{name} guardado en el almacén cifrado del sistema."


def main() -> None:
    """Punto de entrada: pide el valor sin eco y lo guarda."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", choices=["DISCORD_TOKEN", "RESOLVER_API_KEY"])
    parser.add_argument("--file", type=Path, help="guarda en un archivo privado (Docker)")
    args = parser.parse_args()
    print(store(args.name, getpass.getpass(f"{args.name} (no se muestra): "), args.file))


if __name__ == "__main__":
    main()
