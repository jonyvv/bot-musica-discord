import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request

from resolver.domain.errors import RateLimitedError

_BUSY = "Hay demasiados pedidos seguidos. Esperá unos segundos."


@dataclass(frozen=True, slots=True)
class SecurityPolicy:
    api_key_sha256: str = ""
    requests_per_minute: int = 120
    max_body_bytes: int = 65_536
    auth_failure_limit: int = 5
    auth_failure_window_seconds: int = 300


class SlidingWindowLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ):
        """Cuenta eventos por clave en una ventana móvil, con memoria acotada ante muchas claves."""
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._max_keys = max_keys
        self._events: dict[str, deque[float]] = {}

    def hit(self, key: str) -> float | None:
        """Registra un evento; devuelve los segundos a esperar si se superó el tope, o None."""
        wait = self.retry_after(key)
        if wait is None:
            self._events.setdefault(key, deque()).append(self._clock())
        return wait

    def retry_after(self, key: str) -> float | None:
        """Segundos hasta que la clave vuelva a tener cupo, o None si todavía lo tiene."""
        now = self._clock()
        events = self._events.get(key)
        if events is None:
            self._make_room(now)
            return None
        while events and now - events[0] >= self._window:
            events.popleft()
        if len(events) < self._limit:
            return None
        return self._window - (now - events[0])

    def _make_room(self, now: float) -> None:
        """Descarta claves vencidas y, si siguen siendo demasiadas, las más antiguas."""
        if len(self._events) < self._max_keys:
            return
        expired = [
            k
            for k, events in self._events.items()
            if not events or now - events[-1] >= self._window
        ]
        for key in expired:
            del self._events[key]
        for key in list(self._events)[: max(len(self._events) - self._max_keys + 1, 0)]:
            del self._events[key]


def client_id(request: Request) -> str:
    """Identifica al cliente por su dirección de red."""
    return request.client.host if request.client else "desconocido"


def throttle_requests(request: Request) -> None:
    """Rechaza con 429 al cliente que supera su cupo de pedidos por minuto."""
    limiter = request.app.state.request_limiter
    if limiter is None:
        return
    wait = limiter.hit(client_id(request))
    if wait is not None:
        raise RateLimitedError(_BUSY, wait)
