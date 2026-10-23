import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum

from bot.application.activity import ActivityFactory, null_activity
from bot.application.clock import PlaybackClock
from bot.application.ports import Notifier, TrackResolver, VoiceGateway
from bot.domain.errors import BotError, InvalidRequestError, NotPlayingError, VoiceError
from bot.domain.models import LoopMode, Resolution, Track
from bot.domain.queue import TrackQueue
from bot.domain.text import escape_markup

logger = logging.getLogger(__name__)

MAX_VOLUME = 150


class PlaybackState(StrEnum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"


@dataclass(frozen=True, slots=True)
class SessionSettings:
    default_volume: int = 50
    max_queue_size: int = 1000
    max_tracks_per_user: int = 200
    max_inflight: int = 3


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    resolution: Resolution
    added: int
    position: int


class GuildSession:
    def __init__(
        self,
        guild_id: int,
        resolver: TrackResolver,
        voice: VoiceGateway,
        notifier: Notifier,
        settings: SessionSettings,
        activity_factory: ActivityFactory = null_activity,
        on_closed: Callable[[int], None] | None = None,
    ):
        """Reproducción de un servidor: cola, estado y coordinación entre resolver y voz."""
        self.guild_id = guild_id
        self.queue = TrackQueue(settings.max_queue_size)
        self.loop_mode = LoopMode.OFF
        self.volume = settings.default_volume
        self.state = PlaybackState.IDLE
        self._settings = settings
        self._inflight = 0
        self._resolver = resolver
        self._voice = voice
        self._notifier = notifier
        self._on_closed = on_closed
        self._clock = PlaybackClock()
        self._lock = asyncio.Lock()
        self._generation = 0
        self._closed = False
        self._observer = activity_factory(self.close)

    @property
    def elapsed(self) -> float:
        """Segundos reproducidos de la canción actual."""
        return self._clock.elapsed

    @property
    def channel_id(self) -> int | None:
        """Canal de voz donde está conectada la sesión, si lo está."""
        return self._voice.channel_id if self._voice.is_connected else None

    def bind_text_channel(self, channel_id: int) -> None:
        """Define el canal de texto donde la sesión publica sus avisos."""
        self._notifier.bind(channel_id)

    async def enqueue(self, query: str, requester_id: int, channel_id: int) -> EnqueueResult:
        """Resuelve el pedido, se conecta y lo encola, arrancando si no había nada sonando."""
        resolution = await self._resolve_limited(query)
        tracks = [replace(track, requester_id=requester_id) for track in resolution.tracks]
        self._ensure_open()
        await self._ensure_connected(channel_id)
        async with self._lock:
            self._ensure_open()
            tracks = tracks[: self._quota_left(requester_id)]
            idle = self.queue.current is None
            position = 0 if idle else len(self.queue) + 1
            added = self.queue.add(tracks)
            if added == 0:
                raise InvalidRequestError("La cola está llena.")
            if idle:
                await self._advance()
        return EnqueueResult(resolution, added, position)

    async def skip(self) -> Track:
        """Corta la canción actual y pasa a la siguiente, aun si está repetida."""
        async with self._lock:
            skipped = self._require_current()
            self._generation += 1
            self._voice.stop()
            await self._advance(force=True)
        return skipped

    def pause(self) -> None:
        """Pausa la canción en curso."""
        if self.state is not PlaybackState.PLAYING:
            raise NotPlayingError("No hay nada reproduciéndose.")
        self._voice.pause()
        self._clock.pause()
        self.state = PlaybackState.PAUSED
        self._observer.paused()

    def resume(self) -> None:
        """Reanuda la canción pausada."""
        if self.state is not PlaybackState.PAUSED:
            raise NotPlayingError("La reproducción no está en pausa.")
        self._voice.resume()
        self._clock.resume()
        self.state = PlaybackState.PLAYING
        self._observer.playing()

    async def stop(self) -> None:
        """Detiene la reproducción y vacía la cola, sin salir del canal."""
        async with self._lock:
            self._generation += 1
            self.queue.reset()
            self._voice.stop()
            self._go_idle()

    def set_volume(self, percent: int) -> None:
        """Cambia el volumen, que se conserva entre canciones."""
        if not 0 <= percent <= MAX_VOLUME:
            raise InvalidRequestError(f"El volumen debe estar entre 0 y {MAX_VOLUME}.")
        self.volume = percent
        self._voice.set_volume(percent)

    def channel_emptied(self) -> None:
        """Avisa que el canal de voz se quedó sin personas."""
        self._observer.channel_empty()

    def channel_occupied(self) -> None:
        """Avisa que el canal de voz volvió a tener personas."""
        self._observer.channel_occupied()

    async def close(self, reason: str | None = None) -> None:
        """Libera todo: corta el audio, sale del canal, vacía la cola y avisa el motivo."""
        if self._closed:
            return
        self._closed = True
        self._generation += 1
        self._observer.close()
        self.queue.reset()
        self._clock.stop()
        self.state = PlaybackState.IDLE
        self._voice.stop()
        await self._voice.disconnect()
        if reason:
            await self._notifier.send(reason)
        if self._on_closed:
            self._on_closed(self.guild_id)

    async def _resolve_limited(self, query: str) -> Resolution:
        """Resuelve el pedido limitando cuántas resoluciones simultáneas puede tener el servidor."""
        if self._inflight >= self._settings.max_inflight:
            raise InvalidRequestError("Hay demasiados pedidos en proceso. Esperá un momento.")
        self._inflight += 1
        try:
            return await self._resolver.resolve(query)
        finally:
            self._inflight -= 1

    def _quota_left(self, requester_id: int) -> int:
        """Cuántas canciones más puede agregar ese usuario; falla si ya llegó a su tope."""
        limit = self._settings.max_tracks_per_user
        if limit <= 0:
            return self._settings.max_queue_size
        queued = [self.queue.current, *self.queue.pending]
        used = sum(1 for track in queued if track and track.requester_id == requester_id)
        if used >= limit:
            raise InvalidRequestError(
                f"Ya tenés {used} canciones en la cola (el máximo es {limit})."
            )
        return limit - used

    def _ensure_open(self) -> None:
        """Falla si la sesión ya fue cerrada mientras se esperaba una operación."""
        if self._closed:
            raise VoiceError("La sesión se cerró; volvé a intentarlo.")

    def _require_current(self) -> Track:
        """Devuelve la canción en curso o falla si no hay ninguna."""
        if self.queue.current is None:
            raise NotPlayingError("No hay nada reproduciéndose.")
        return self.queue.current

    async def _ensure_connected(self, channel_id: int) -> None:
        """Conecta al canal pedido solo si todavía no está en él."""
        if not self._voice.is_connected or self._voice.channel_id != channel_id:
            await self._voice.connect(channel_id)

    async def _advance(self, force: bool = False) -> None:
        """Pasa a la siguiente canción reproducible o deja la sesión inactiva."""
        while not self._closed and (track := self.queue.advance(self.loop_mode, force)):
            if await self._start(track):
                return
            force = True
        self._go_idle()

    async def _start(self, track: Track) -> bool:
        """Obtiene el stream de la canción y la reproduce; avisa y devuelve False si falla."""
        self._generation += 1
        generation = self._generation

        async def on_finished(error: Exception | None) -> None:
            """Reenvía el fin de la canción asociándolo a esta reproducción."""
            await self._handle_finished(generation, error)

        try:
            stream = await self._resolver.stream(track)
            if self._closed:
                return False
            await self._voice.play(stream, self.volume, on_finished)
        except BotError as exc:
            title = escape_markup(track.title)
            await self._notifier.send(f"No pude reproducir **{title}**: {exc.user_message}")
            return False
        self.state = PlaybackState.PLAYING
        self._clock.start()
        self._observer.playing()
        return True

    async def _handle_finished(self, generation: int, error: Exception | None) -> None:
        """Avanza la cola al terminar una canción, ignorando avisos de reproducciones viejas."""
        if self._closed or generation != self._generation:
            return
        if error is not None:
            logger.warning("Error de reproduccion en guild %s: %s", self.guild_id, error)
        async with self._lock:
            if self._closed or generation != self._generation:
                return
            await self._advance()

    def _go_idle(self) -> None:
        """Marca la sesión como inactiva y lo comunica al observador."""
        if self._closed:
            return
        self.state = PlaybackState.IDLE
        self._clock.stop()
        self._observer.idle()
