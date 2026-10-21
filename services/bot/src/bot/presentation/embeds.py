import math

import discord

from bot.application.session import EnqueueResult, GuildSession, PlaybackState
from bot.domain.errors import InvalidRequestError, NotPlayingError
from bot.domain.models import LoopMode, Track
from bot.presentation.formatting import format_duration, progress_bar, safe

PAGE_SIZE = 10
COLOR = discord.Color.blurple()
_LOOP_LABELS = {
    LoopMode.OFF: "desactivada",
    LoopMode.TRACK: "canción actual",
    LoopMode.QUEUE: "toda la cola",
}


def loop_label(mode: LoopMode) -> str:
    """Nombre en español de un modo de repetición."""
    return _LOOP_LABELS[mode]


def track_link(track: Track) -> str:
    """Título de la canción como enlace a su fuente cuando se conoce."""
    title = safe(track.title)
    return f"[{title}]({track.webpage_url})" if track.webpage_url else f"**{title}**"


def now_playing_embed(session: GuildSession) -> discord.Embed:
    """Arma el panel de la canción que está sonando, con progreso y datos de quién la pidió."""
    track = session.queue.current
    if track is None:
        raise NotPlayingError("No hay nada reproduciéndose.")
    paused = session.state is PlaybackState.PAUSED
    embed = discord.Embed(
        title="⏸️ En pausa" if paused else "▶️ Reproduciendo",
        description=track_link(track),
        color=COLOR,
    )
    embed.add_field(name="Artista", value=safe(track.artist or "Desconocido", 40))
    if track.requester_id:
        embed.add_field(name="Pedida por", value=f"<@{track.requester_id}>")
    embed.add_field(name="Volumen", value=f"{session.volume}%")
    if track.is_live:
        embed.add_field(name="Duración", value="🔴 En vivo", inline=False)
    elif track.duration_seconds:
        bar = progress_bar(session.elapsed, track.duration_seconds)
        times = f"{format_duration(session.elapsed)} / {format_duration(track.duration_seconds)}"
        embed.add_field(name="Progreso", value=f"{bar}\n{times}", inline=False)
    if track.thumbnail_url:
        embed.set_thumbnail(url=track.thumbnail_url)
    embed.set_footer(text=f"Repetir: {loop_label(session.loop_mode)}")
    return embed


def queue_embed(session: GuildSession, page: int) -> discord.Embed:
    """Arma una página de la cola con la canción actual, las pendientes y el tiempo restante."""
    pending = session.queue.pending
    pages = max(1, math.ceil(len(pending) / PAGE_SIZE))
    if page > pages:
        raise InvalidRequestError(f"Solo hay {pages} página(s) en la cola.")
    start = (page - 1) * PAGE_SIZE
    lines = [
        f"`{start + offset}.` {track_link(track)} · {format_duration(track.duration_seconds)}"
        for offset, track in enumerate(pending[start : start + PAGE_SIZE], start=1)
    ]
    embed = discord.Embed(
        title="Cola de reproducción",
        description="\n".join(lines) or "La cola está vacía.",
        color=COLOR,
    )
    if session.queue.current:
        embed.add_field(name="Sonando ahora", value=track_link(session.queue.current), inline=False)
    embed.set_footer(
        text=(
            f"Página {page}/{pages} · {len(pending)} en cola · "
            f"{format_duration(session.queue.pending_seconds)} restantes · "
            f"Repetir: {loop_label(session.loop_mode)}"
        )
    )
    return embed


def enqueued_embed(result: EnqueueResult) -> discord.Embed:
    """Arma la confirmación de lo que se agregó a la cola tras un pedido de reproducción."""
    resolution = result.resolution
    if len(resolution.tracks) == 1:
        track = resolution.tracks[0]
        title = (
            "▶️ Reproduciendo ahora"
            if result.position == 0
            else f"➕ Agregada a la cola (posición {result.position})"
        )
        embed = discord.Embed(title=title, description=track_link(track), color=COLOR)
        embed.add_field(name="Duración", value=format_duration(track.duration_seconds))
        if track.thumbnail_url:
            embed.set_thumbnail(url=track.thumbnail_url)
        return embed
    where = (
        "Empieza a sonar ahora."
        if result.position == 0
        else f"La primera quedó en la posición {result.position}."
    )
    source = f"De **{safe(resolution.title)}**.\n" if resolution.title else ""
    embed = discord.Embed(
        title=f"➕ Agregadas {result.added} canciones",
        description=f"{source}{where}",
        color=COLOR,
    )
    if result.added < len(resolution.tracks):
        embed.add_field(
            name="Cola llena", value=f"Solo entraron {result.added} de {len(resolution.tracks)}."
        )
    if resolution.truncated:
        embed.add_field(
            name="Lista recortada", value="La lista era más larga que el máximo permitido."
        )
    return embed
