SERVICE = "bot-musica-discord"


def load_secret(name: str) -> str | None:
    """Lee un secreto del almacén cifrado del sistema; None si no hay almacén o no existe."""
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError:
        return None
    try:
        return keyring.get_password(SERVICE, name) or None
    except KeyringError:
        return None


def save_secret(name: str, value: str) -> None:
    """Guarda un secreto en el almacén cifrado del sistema (en Windows, el Administrador)."""
    import keyring

    keyring.set_password(SERVICE, name, value)
