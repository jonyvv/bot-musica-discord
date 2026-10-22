import asyncio
import time
from collections.abc import Awaitable, Callable


class Pacer:
    def __init__(
        self,
        max_concurrent: int,
        min_interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        """Limita cuántas consultas a YouTube corren a la vez y las espacia en el tiempo."""
        self._slots = asyncio.Semaphore(max_concurrent)
        self._interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._next_free = 0.0
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> None:
        """Espera un cupo de simultaneidad y el turno que corresponde según el espaciado."""
        await self._slots.acquire()
        try:
            async with self._lock:
                start = max(self._clock(), self._next_free)
                self._next_free = start + self._interval
            if (wait := start - self._clock()) > 0:
                await self._sleep(wait)
        except BaseException:
            self._slots.release()
            raise

    async def __aexit__(self, *_: object) -> None:
        """Libera el cupo de simultaneidad."""
        self._slots.release()
