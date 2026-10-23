from collections.abc import Awaitable, Callable

from bot.application.ports import ActivityObserver

CloseSession = Callable[[str | None], Awaitable[None]]
ActivityFactory = Callable[[CloseSession], ActivityObserver]


class NullActivityObserver:
    def playing(self) -> None:
        """Ignora el inicio de una reproducción."""

    def paused(self) -> None:
        """Ignora la pausa."""

    def idle(self) -> None:
        """Ignora la inactividad."""

    def channel_empty(self) -> None:
        """Ignora que el canal se haya quedado vacío."""

    def channel_occupied(self) -> None:
        """Ignora que el canal vuelva a tener personas."""

    def close(self) -> None:
        """Ignora el cierre de la sesión."""


def null_activity(_: CloseSession) -> ActivityObserver:
    """Fábrica por defecto de observador: no hace nada ante los cambios de actividad."""
    return NullActivityObserver()
