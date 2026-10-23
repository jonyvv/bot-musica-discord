import logging

import discord
from discord.ext import commands

from bot.application.registry import SessionRegistry
from bot.presentation.cogs.events import VoiceEventsCog
from bot.presentation.cogs.playback import PlaybackCog
from bot.presentation.cogs.queue import QueueCog
from bot.presentation.errors import handle_command_error
from bot.presentation.limits import InteractionGate
from bot.presentation.permissions import risky_permissions

logger = logging.getLogger(__name__)


class MusicBot(commands.Bot):
    def __init__(
        self,
        registry: SessionRegistry,
        guild_id: int | None = None,
        gate: InteractionGate | None = None,
    ):
        """Bot de Discord que solo usa comandos slash, por lo que no necesita leer mensajes."""
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=discord.Intents.default(),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        self.registry = registry
        self.gate = gate or InteractionGate()
        self._guild_id = guild_id
        self.tree.interaction_check = self.gate.check

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
        """Se retira de los servidores no permitidos y registra que ya está conectado."""
        for guild in self.guilds:
            await self.leave_if_not_allowed(guild)
        logger.info("Conectado como %s en %d servidor(es)", self.user, len(self.guilds))

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Se retira de inmediato si lo agregaron a un servidor que no está permitido."""
        await self.leave_if_not_allowed(guild)

    async def leave_if_not_allowed(self, guild: discord.Guild) -> None:
        """Abandona el servidor si no está permitido; si lo está, avisa de permisos excesivos."""
        if not self.gate.allows(guild.id):
            logger.warning("Servidor no permitido (%s): el bot lo abandona", guild.id)
            await guild.leave()
            return
        if risky := risky_permissions(guild.me.guild_permissions):
            logger.warning(
                "El bot tiene permisos que no necesita en %s: %s. Quitáselos a su rol.",
                guild.id,
                ", ".join(risky),
            )

    async def close(self) -> None:
        """Cierra todas las sesiones de música antes de apagar el bot."""
        for session in self.registry.sessions():
            await session.close()
        await super().close()
