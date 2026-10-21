import discord
from discord import app_commands
from discord.ext import commands

from bot.application.registry import SessionRegistry
from bot.domain.errors import InvalidRequestError
from bot.domain.models import LoopMode
from bot.presentation.embeds import loop_label, queue_embed
from bot.presentation.formatting import safe
from bot.presentation.guards import controlled_session, existing_session

_LOOP_CHOICES = [
    app_commands.Choice(name="Desactivada", value=LoopMode.OFF.value),
    app_commands.Choice(name="Canción actual", value=LoopMode.TRACK.value),
    app_commands.Choice(name="Toda la cola", value=LoopMode.QUEUE.value),
]


class QueueCog(commands.Cog):
    def __init__(self, registry: SessionRegistry):
        """Comandos para ver y modificar la cola de reproducción."""
        self._registry = registry

    @app_commands.command(name="queue", description="Muestra la cola de reproducción")
    @app_commands.describe(page="Número de página")
    @app_commands.guild_only()
    async def queue(
        self, interaction: discord.Interaction, page: app_commands.Range[int, 1] = 1
    ) -> None:
        """Muestra una página de la cola."""
        session = existing_session(interaction, self._registry)
        await interaction.response.send_message(embed=queue_embed(session, page))

    @app_commands.command(name="remove", description="Quita una canción de la cola")
    @app_commands.describe(position="Posición en la cola, empezando en 1")
    @app_commands.guild_only()
    async def remove(
        self, interaction: discord.Interaction, position: app_commands.Range[int, 1]
    ) -> None:
        """Quita la canción pendiente en la posición indicada."""
        track = controlled_session(interaction, self._registry).queue.remove(position)
        await interaction.response.send_message(f"🗑️ Quité **{safe(track.title)}** de la cola.")

    @app_commands.command(name="clear", description="Vacía la cola sin cortar la canción actual")
    @app_commands.guild_only()
    async def clear(self, interaction: discord.Interaction) -> None:
        """Vacía las canciones pendientes."""
        removed = controlled_session(interaction, self._registry).queue.clear()
        await interaction.response.send_message(f"🧹 Vacié la cola ({removed} canciones).")

    @app_commands.command(name="shuffle", description="Mezcla la cola")
    @app_commands.guild_only()
    async def shuffle(self, interaction: discord.Interaction) -> None:
        """Mezcla las canciones pendientes."""
        queue = controlled_session(interaction, self._registry).queue
        if len(queue) < 2:
            raise InvalidRequestError("Necesito al menos 2 canciones en la cola para mezclar.")
        queue.shuffle()
        await interaction.response.send_message("🔀 Mezclé la cola.")

    @app_commands.command(name="loop", description="Configura la repetición")
    @app_commands.describe(mode="Qué repetir")
    @app_commands.choices(mode=_LOOP_CHOICES)
    @app_commands.guild_only()
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]) -> None:
        """Cambia el modo de repetición de la sesión."""
        session = controlled_session(interaction, self._registry)
        session.loop_mode = LoopMode(mode.value)
        await interaction.response.send_message(f"🔁 Repetición: {loop_label(session.loop_mode)}.")
