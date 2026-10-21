import logging

import discord
from discord.ext import commands

from bot.application.registry import SessionRegistry
from bot.presentation.cogs.events import VoiceEventsCog
from bot.presentation.cogs.playback import PlaybackCog
from bot.presentation.cogs.queue import QueueCog
from bot.presentation.errors import handle_command_error

logger = logging.getLogger(__name__)


class MusicBot(commands.Bot):
    def __init__(self, registry: SessionRegistry, guild_id: int | None = None):
        """Bot de Discord que solo usa comandos slash, por lo que no necesita leer mensajes."""
        super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.default())
        self.registry = registry
        self._guild_id = guild_id

    async def setup_hook(self) -> None:
        """Registra los comandos y los sincroniza con Discord al iniciar."""
        await self.register_cogs()
        self.tree.on_error = handle_command_error
        await self.sync_commands()

    async def register_cogs(self) -> None:
        """Agrega los grupos de comandos y el listener de eventos de voz."""
        for cog in (
            PlaybackCog(self.registry),
            QueueCog(self.registry),
            VoiceEventsCog(self.registry),
        ):
            await self.add_cog(cog)

    async def sync_commands(self) -> None:
        """Publica los comandos; en un servidor puntual aparecen al instante, globales tardan."""
        if self._guild_id:
            guild = discord.Object(id=self._guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        """Registra que el bot ya está conectado a Discord."""
        logger.info("Conectado como %s en %d servidor(es)", self.user, len(self.guilds))

    async def close(self) -> None:
        """Cierra todas las sesiones de música antes de apagar el bot."""
        for session in self.registry.sessions():
            await session.close()
        await super().close()
