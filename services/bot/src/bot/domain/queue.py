import random
from collections import deque
from collections.abc import Iterable

from bot.domain.errors import InvalidRequestError
from bot.domain.models import LoopMode, Track


class TrackQueue:
    def __init__(self, max_size: int):
        """Cola de canciones pendientes junto con la canción en curso, acotada por `max_size`."""
        self._max_size = max_size
        self._pending: deque[Track] = deque()
        self.current: Track | None = None

    def __len__(self) -> int:
        """Cantidad de canciones pendientes, sin contar la que está sonando."""
        return len(self._pending)

    @property
    def pending(self) -> tuple[Track, ...]:
        """Copia inmutable de las canciones pendientes en orden de reproducción."""
        return tuple(self._pending)

    @property
    def pending_seconds(self) -> int:
        """Duración total de las canciones pendientes que tienen duración conocida."""
        return sum(t.duration_seconds or 0 for t in self._pending)

    def add(self, tracks: Iterable[Track]) -> int:
        """Agrega canciones al final hasta llenar la cola y devuelve cuántas entraron."""
        room = self._max_size - len(self._pending)
        accepted = list(tracks)[: max(room, 0)]
        self._pending.extend(accepted)
        return len(accepted)

    def advance(self, loop_mode: LoopMode, force: bool = False) -> Track | None:
        """Pasa a la siguiente canción según el modo de repetición; `force` ignora repetir una."""
        previous = self.current
        if previous is not None:
            if loop_mode is LoopMode.TRACK and not force:
                return previous
            if loop_mode is LoopMode.QUEUE:
                self._pending.append(previous)
        self.current = self._pending.popleft() if self._pending else None
        return self.current

    def remove(self, position: int) -> Track:
        """Quita y devuelve la canción pendiente en la posición indicada, contando desde 1."""
        if not 1 <= position <= len(self._pending):
            raise InvalidRequestError(f"La posición debe estar entre 1 y {len(self._pending)}.")
        track = self._pending[position - 1]
        del self._pending[position - 1]
        return track

    def clear(self) -> int:
        """Vacía las canciones pendientes y devuelve cuántas había."""
        removed = len(self._pending)
        self._pending.clear()
        return removed

    def shuffle(self, rng: random.Random | None = None) -> None:
        """Mezcla las canciones pendientes sin tocar la que está sonando."""
        items = list(self._pending)
        (rng or random).shuffle(items)
        self._pending = deque(items)

    def reset(self) -> None:
        """Descarta tanto las pendientes como la canción en curso."""
        self._pending.clear()
        self.current = None
