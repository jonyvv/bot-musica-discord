import time
from collections.abc import Callable


class PlaybackClock:
    def __init__(self, now: Callable[[], float] = time.monotonic):
        """Cronómetro de reproducción que descuenta los tiempos en pausa."""
        self._now = now
        self._accumulated = 0.0
        self._started_at: float | None = None

    @property
    def elapsed(self) -> float:
        """Segundos reproducidos de la canción actual."""
        if self._started_at is None:
            return self._accumulated
        return self._accumulated + self._now() - self._started_at

    def start(self) -> None:
        """Arranca el conteo desde cero."""
        self._accumulated = 0.0
        self._started_at = self._now()

    def pause(self) -> None:
        """Congela el conteo conservando lo acumulado."""
        self._accumulated = self.elapsed
        self._started_at = None

    def resume(self) -> None:
        """Retoma el conteo desde lo acumulado."""
        if self._started_at is None:
            self._started_at = self._now()

    def stop(self) -> None:
        """Detiene el conteo y lo deja en cero."""
        self._accumulated = 0.0
        self._started_at = None
