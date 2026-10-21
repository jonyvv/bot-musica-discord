from collections.abc import Awaitable, Callable
from typing import Protocol

from bot.domain.models import Resolution, StreamInfo, Track

FinishedCallback = Callable[[Exception | None], Awaitable[None]]


class TrackResolver(Protocol):
    async def resolve(self, query: str) -> Resolution:
        """Convierte un link o texto de búsqueda en canciones."""
        ...

    async def stream(self, track: Track) -> StreamInfo:
        """Obtiene el audio reproducible de una canción."""
        ...


class VoiceGateway(Protocol):
    @property
    def is_connected(self) -> bool:
        """Indica si hay una conexión de voz activa."""
        ...

    @property
    def channel_id(self) -> int | None:
        """Identificador del canal de voz actual, si hay conexión."""
        ...

    async def connect(self, channel_id: int) -> None:
        """Se conecta al canal de voz o se mueve a él."""
        ...

    async def disconnect(self) -> None:
        """Cierra la conexión de voz."""
        ...

    async def play(self, stream: StreamInfo, volume: int, on_finished: FinishedCallback) -> None:
        """Reproduce el stream y avisa con `on_finished` cuando termina o falla."""
        ...

    def pause(self) -> None:
        """Pausa el audio en curso."""
        ...

    def resume(self) -> None:
        """Reanuda el audio pausado."""
        ...

    def stop(self) -> None:
        """Detiene el audio en curso."""
        ...

    def set_volume(self, volume: int) -> None:
        """Cambia el volumen del audio en curso, en porcentaje."""
        ...


class Notifier(Protocol):
    def bind(self, channel_id: int) -> None:
        """Define el canal de texto donde se publican los avisos."""
        ...

    async def send(self, text: str) -> None:
        """Publica un aviso en el canal de texto asociado."""
        ...


class ActivityObserver(Protocol):
    def playing(self) -> None:
        """Se llama cuando empieza o se reanuda una reproducción."""
        ...

    def paused(self) -> None:
        """Se llama cuando la reproducción se pausa."""
        ...

    def idle(self) -> None:
        """Se llama cuando no queda nada por reproducir."""
        ...

    def channel_empty(self) -> None:
        """Se llama cuando el canal de voz se queda sin personas."""
        ...

    def channel_occupied(self) -> None:
        """Se llama cuando vuelve a haber personas en el canal de voz."""
        ...

    def close(self) -> None:
        """Libera los recursos del observador al terminar la sesión."""
        ...
