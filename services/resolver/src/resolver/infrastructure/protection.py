import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from resolver.application.ports import MediaExtractor
from resolver.domain.errors import BotDetectedError
from resolver.domain.models import Resolution, StreamInfo, Track
from resolver.infrastructure.pacing import Pacer

_PAUSED = "Pausé las consultas a YouTube unos minutos porque nos marcó como bot. Probá más tarde."
_STREAM_MARGIN_SECONDS = 60


@dataclass(slots=True)
class _Entry:
    value: Any
    expires_at: float


class CircuitBreaker:
    def __init__(
        self,
        threshold: int = 3,
        cooldown_seconds: float = 600.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        """Deja de consultar a YouTube un rato tras varias detecciones de bot seguidas."""
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._failures = 0
        self._open_until = 0.0

    def before_call(self) -> None:
        """Falla de inmediato, sin tocar la red, mientras el cortacircuito está abierto."""
        if self._clock() < self._open_until:
            raise BotDetectedError(_PAUSED)

    def record_success(self) -> None:
        """Reinicia la cuenta de fallos tras una consulta exitosa."""
        self._failures = 0

    def record_failure(self) -> None:
        """Cuenta una detección de bot y abre el cortacircuito al llegar al umbral."""
        self._failures += 1
        if self._failures >= self._threshold:
            self._open_until = self._clock() + self._cooldown
            self._failures = self._threshold - 1


class ProtectedExtractor:
    def __init__(
        self,
        inner: MediaExtractor,
        pacer: Pacer,
        breaker: CircuitBreaker,
        ttl_seconds: float = 600.0,
        max_entries: int = 256,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ):
        """Cuida el tráfico hacia YouTube: caché, consulta única por pedido repetido, espaciado."""
        self._inner = inner
        self._pacer = pacer
        self._breaker = breaker
        self._ttl = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._wall_clock = wall_clock
        self._cache: dict[tuple, _Entry] = {}
        self._inflight: dict[tuple, asyncio.Future] = {}

    async def video(self, url: str) -> Track:
        """Obtiene los metadatos de un video, reutilizando consultas recientes."""
        return await self._run(("video", url), lambda: self._inner.video(url))

    async def playlist(self, url: str, limit: int) -> Resolution:
        """Obtiene una playlist, reutilizando consultas recientes."""
        return await self._run(("playlist", url, limit), lambda: self._inner.playlist(url, limit))

    async def search(self, query: str, count: int) -> list[Track]:
        """Busca candidatos, reutilizando consultas recientes."""
        return await self._run(("search", query, count), lambda: self._inner.search(query, count))

    async def stream(self, url: str) -> StreamInfo:
        """Obtiene el audio de un video; el resultado se guarda hasta poco antes de que venza."""
        return await self._run(("stream", url), lambda: self._inner.stream(url), self._stream_ttl)

    async def _run(
        self,
        key: tuple,
        call: Callable[[], Awaitable[Any]],
        ttl_of: Callable[[Any], float] | None = None,
    ) -> Any:
        """Resuelve desde la caché o, si no está, con una única consulta compartida por todos."""
        if (entry := self._cache.get(key)) and entry.expires_at > self._clock():
            return entry.value
        pending = self._inflight.get(key)
        if pending is None:
            pending = asyncio.ensure_future(self._fetch(key, call, ttl_of))
            self._inflight[key] = pending
            pending.add_done_callback(lambda _: self._inflight.pop(key, None))
        return await asyncio.shield(pending)

    async def _fetch(self, key: tuple, call: Callable[[], Awaitable[Any]], ttl_of) -> Any:
        """Hace la consulta real bajo el cortacircuito y el espaciado, y guarda el resultado."""
        self._breaker.before_call()
        async with self._pacer:
            try:
                result = await call()
            except BotDetectedError:
                self._breaker.record_failure()
                raise
        self._breaker.record_success()
        self._store(key, result, ttl_of(result) if ttl_of else self._ttl)
        return result

    def _stream_ttl(self, stream: StreamInfo) -> float:
        """Vigencia en caché de un stream: la normal, sin pasar del vencimiento de su URL."""
        if stream.expires_at is None:
            return self._ttl
        remaining = stream.expires_at - self._wall_clock() - _STREAM_MARGIN_SECONDS
        return min(self._ttl, remaining)

    def _store(self, key: tuple, value: Any, ttl: float) -> None:
        """Guarda un resultado con su vigencia, acotando el tamaño total de la caché."""
        if ttl <= 0:
            return
        now = self._clock()
        if len(self._cache) >= self._max_entries:
            for stale in [k for k, e in self._cache.items() if e.expires_at <= now]:
                del self._cache[stale]
            for oldest in list(self._cache)[: max(len(self._cache) - self._max_entries + 1, 0)]:
                del self._cache[oldest]
        self._cache[key] = _Entry(value, now + ttl)
