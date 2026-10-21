from dataclasses import dataclass

from bot.application.activity import CloseSession
from bot.application.timers import TimerRegistry

IDLE = "idle"
PAUSE = "pause"
EMPTY = "empty"

IDLE_MESSAGE = "Me desconecté por inactividad."
PAUSE_MESSAGE = "Me desconecté porque la reproducción estuvo pausada demasiado tiempo."
EMPTY_MESSAGE = "Me desconecté porque me quedé solo en el canal de voz."


@dataclass(frozen=True, slots=True)
class Timeouts:
    idle: int = 300
    pause: int = 600
    empty: int = 120


class InactivityPolicy:
    def __init__(self, timers: TimerRegistry, timeouts: Timeouts, close: CloseSession):
        """Desconecta por inactividad, pausa larga o canal vacío; un plazo en 0 se desactiva."""
        self._timers = timers
        self._timeouts = timeouts
        self._close = close

    def playing(self) -> None:
        """Cancela los plazos de inactividad y de pausa porque vuelve a sonar música."""
        self._timers.cancel(IDLE)
        self._timers.cancel(PAUSE)

    def paused(self) -> None:
        """Arranca el plazo de pausa prolongada."""
        self._timers.cancel(IDLE)
        self._arm(PAUSE, self._timeouts.pause, PAUSE_MESSAGE)

    def idle(self) -> None:
        """Arranca el plazo de inactividad porque no queda nada por reproducir."""
        self._timers.cancel(PAUSE)
        self._arm(IDLE, self._timeouts.idle, IDLE_MESSAGE)

    def channel_empty(self) -> None:
        """Arranca el plazo de canal vacío, que corre aunque haya música sonando."""
        self._arm(EMPTY, self._timeouts.empty, EMPTY_MESSAGE)

    def channel_occupied(self) -> None:
        """Cancela el plazo de canal vacío porque volvió alguien."""
        self._timers.cancel(EMPTY)

    def close(self) -> None:
        """Cancela todos los plazos al cerrar la sesión."""
        self._timers.cancel_all()

    def _arm(self, name: str, seconds: int, message: str) -> None:
        """Programa la desconexión con su mensaje, salvo que el plazo esté desactivado."""
        if seconds <= 0:
            return

        async def expire() -> None:
            """Cierra la sesión explicando el motivo."""
            await self._close(message)

        self._timers.start(name, seconds, expire)
