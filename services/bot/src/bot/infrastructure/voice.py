import asyncio
import logging

import discord
from discord.ext import commands

from bot.application.ports import FinishedCallback
from bot.domain.errors import VoiceError
from bot.domain.models import StreamInfo
from bot.infrastructure.ffmpeg import OUTPUT_OPTIONS, before_options

logger = logging.getLogger(__name__)


class DiscordVoiceGateway:
    def __init__(self, bot: commands.Bot, guild_id: int):
        """Adaptador de la conexión de voz de un servidor de Discord con FFmpeg."""
        self._bot = bot
        self._guild_id = guild_id

    @property
    def is_connected(self) -> bool:
        """Indica si hay una conexión de voz activa."""
        client = self._client
        return client is not None and client.is_connected()

    @property
    def channel_id(self) -> int | None:
        """Identificador del canal de voz actual, si hay conexión."""
        client = self._client
        return client.channel.id if client is not None and client.channel else None

    async def connect(self, channel_id: int) -> None:
        """Se conecta al canal de voz o se mueve a él si ya estaba en otro."""
        guild = self._bot.get_guild(self._guild_id)
        channel = guild.get_channel(channel_id) if guild else None
        if channel is None:
            raise VoiceError("No encontré ese canal de voz.")
        try:
            client = self._client
            if client is not None and client.is_connected():
                await client.move_to(channel)
                return
            if client is not None:
                await client.disconnect(force=True)
            await channel.connect(self_deaf=True)
        except (discord.DiscordException, TimeoutError) as exc:
            logger.warning("No se pudo conectar al canal %s: %s", channel_id, exc)
            raise VoiceError("No pude conectarme al canal de voz.") from exc

    async def disconnect(self) -> None:
        """Cierra la conexión de voz si existe."""
        client = self._client
        if client is not None:
            await client.disconnect(force=True)

    async def play(self, stream: StreamInfo, volume: int, on_finished: FinishedCallback) -> None:
        """Reproduce el stream con FFmpeg y avisa cuando termina o falla."""
        client = self._client
        if client is None or not client.is_connected():
            raise VoiceError("No estoy conectado a un canal de voz.")
        loop = asyncio.get_running_loop()

        def after(error: Exception | None) -> None:
            """Devuelve al event loop el aviso de fin, que llega desde el hilo de audio."""
            asyncio.run_coroutine_threadsafe(on_finished(error), loop)

        try:
            audio = discord.FFmpegPCMAudio(
                stream.url, before_options=before_options(stream.headers), options=OUTPUT_OPTIONS
            )
            client.play(discord.PCMVolumeTransformer(audio, volume=volume / 100), after=after)
        except discord.DiscordException as exc:
            logger.warning("No se pudo iniciar el audio: %s", exc)
            raise VoiceError("No pude iniciar el audio. Revisá que FFmpeg esté instalado.") from exc

    def pause(self) -> None:
        """Pausa el audio en curso."""
        if (client := self._client) is not None:
            client.pause()

    def resume(self) -> None:
        """Reanuda el audio pausado."""
        if (client := self._client) is not None:
            client.resume()

    def stop(self) -> None:
        """Detiene el audio en curso."""
        if (client := self._client) is not None:
            client.stop()

    def set_volume(self, volume: int) -> None:
        """Cambia el volumen del audio en curso, en porcentaje."""
        client = self._client
        if client is not None and isinstance(client.source, discord.PCMVolumeTransformer):
            client.source.volume = volume / 100

    @property
    def _client(self) -> discord.VoiceClient | None:
        """Cliente de voz de discord.py asociado al servidor, si existe."""
        guild = self._bot.get_guild(self._guild_id)
        return guild.voice_client if guild else None
