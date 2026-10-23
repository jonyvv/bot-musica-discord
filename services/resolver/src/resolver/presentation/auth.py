import hashlib
import hmac

from fastapi import Request

from resolver.domain.errors import RateLimitedError, UnauthorizedError
from resolver.presentation.security import client_id

_REJECTED = "El servicio de música rechazó las credenciales del bot."
_LOCKED = "Demasiados intentos con una clave inválida. Esperá antes de volver a intentar."


def hash_api_key(key: str) -> str:
    """Calcula el SHA-256 hexadecimal de la clave: es lo único que el resolver necesita guardar."""
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(request: Request) -> None:
    """Exige la clave configurada; tras varios intentos inválidos bloquea al cliente un rato."""
    expected = request.app.state.api_key_sha256
    if not expected:
        return
    failures = request.app.state.auth_failures
    client = client_id(request)
    if (wait := failures.retry_after(client)) is not None:
        raise RateLimitedError(_LOCKED, wait)
    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    matches = hmac.compare_digest(hash_api_key(supplied.strip()), expected.lower())
    if scheme.lower() != "bearer" or not matches:
        failures.hit(client)
        raise UnauthorizedError(_REJECTED)
