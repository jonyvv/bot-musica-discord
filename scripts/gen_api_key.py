"""Genera la clave que autentica al bot frente al resolver, sin mostrarla en pantalla."""

import argparse
import secrets
import shutil
from collections.abc import Callable
from enum import Enum
from pathlib import Path

from secret_files import write_private

from bot.infrastructure.secret_store import save_secret
from resolver.presentation.auth import hash_api_key

ROOT = Path(__file__).resolve().parents[1]
HASH_NAME = "RESOLVER_API_KEY_SHA256"
KEY_NAME = "RESOLVER_API_KEY"


class Outcome(Enum):
    """Resultado de generar la clave; la salida del script nunca incluye la clave."""

    EXISTS = "exists"
    FILES = "files"
    VAULT = "vault"
    ENV_FALLBACK = "env_fallback"


MESSAGES = {
    Outcome.EXISTS: "Ya existe una clave. Usá --force para generar otra y reemplazarla.",
    Outcome.FILES: "Clave generada. Archivos de secreto creados y hash guardado en .env.",
    Outcome.VAULT: "Clave generada. Guardada en el almacén cifrado; su hash está en .env.",
    Outcome.ENV_FALLBACK: "No hay almacén cifrado: la clave quedó en .env. Protegé ese archivo.",
}


def set_env_value(path: Path, name: str, value: str) -> None:
    """Escribe o reemplaza una variable en un archivo .env, conservando el resto."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    entry = f"{name}={value}"
    updated = [entry if line.split("=", 1)[0].strip() == name else line for line in lines]
    if entry not in updated:
        updated.append(entry)
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def has_value(path: Path, name: str) -> bool:
    """Indica si el .env ya define esa variable con algún valor."""
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() == name and value.strip():
            return True
    return False


def generate(
    env_path: Path,
    secrets_dir: Path | None = None,
    force: bool = False,
    store: Callable[[str, str], None] = save_secret,
    make_key: Callable[[int], str] = secrets.token_urlsafe,
) -> Outcome:
    """Crea la clave, guarda su hash en .env y la clave en el almacén cifrado o en archivos."""
    if has_value(env_path, HASH_NAME) and not force:
        return Outcome.EXISTS
    key = make_key(32)
    if not env_path.exists() and (ROOT / ".env.example").exists():
        shutil.copy(ROOT / ".env.example", env_path)
    set_env_value(env_path, HASH_NAME, hash_api_key(key))
    if secrets_dir is not None:
        write_private(secrets_dir / "resolver_api_key", key)
        write_private(secrets_dir / "resolver_api_key_sha256", hash_api_key(key))
        return Outcome.FILES
    try:
        store(KEY_NAME, key)
    except Exception:
        set_env_value(env_path, KEY_NAME, key)
        return Outcome.ENV_FALLBACK
    return Outcome.VAULT


def main() -> None:
    """Punto de entrada: interpreta los argumentos y muestra el resultado sin revelar la clave."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="reemplaza una clave existente")
    parser.add_argument("--secrets-dir", type=Path, help="carpeta de secretos de Docker")
    args = parser.parse_args()
    print(MESSAGES[generate(ROOT / ".env", args.secrets_dir, args.force)])


if __name__ == "__main__":
    main()
