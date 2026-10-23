import discord
from discord import app_commands
from discord.ext import commands

from bot.application.registry import SessionRegistry
from bot.application.session import MAX_VOLUME
from bot.presentation.embeds import enqueued_embed, now_playing_embed
from bot.presentation.formatting import safe
from bot.presentation.guards import controlled_session, existing_session, play_target


class PlaybackCog(commands.Cog):
    def __init__(self, registry: SessionRegistry):
        """Comandos para reproducir y controlar la canción en curso."""
        self._registry = registry

    @app_commands.command(
        name="play", description="Reproduce un link de YouTube/Spotify o busca por nombre"
    )
    @app_commands.describe(query="Link de YouTube o Spotify, o el nombre de la canción")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, 2.0)
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        """Agrega lo pedido a la cola y empieza a sonar si no había nada reproduciéndose."""
        session, channel = play_target(interaction, self._registry)
        await interaction.response.defer()
        session.bind_text_channel(interaction.channel_id)
        result = await session.enqueue(query, interaction.user.id, channel.id)
        await interaction.followup.send(embed=enqueued_embed(result))

    @app_commands.command(name="skip", description="Salta la canción actual")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction) -> None:
        """Corta la canción actual y pasa a la siguiente."""
        skipped = await controlled_session(interaction, self._registry).skip()
        await interaction.response.send_message(f"⏭️ Salté **{safe(skipped.title)}**.")

    @app_commands.command(name="pause", description="Pausa la reproducción")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction) -> None:
        """Pausa la canción en curso."""
        controlled_session(interaction, self._registry).pause()
        await interaction.response.send_message("⏸️ Pausado.")

    @app_commands.command(name="resume", description="Reanuda la reproducción")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction) -> None:
        """Reanuda la canción pausada."""
        controlled_session(interaction, self._registry).resume()
        await interaction.response.send_message("▶️ Reanudado.")

    @app_commands.command(name="stop", description="Detiene la música y vacía la cola")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction) -> None:
        """Detiene la reproducción y vacía la cola sin salir del canal."""
        await controlled_session(interaction, self._registry).stop()
        await interaction.response.send_message("⏹️ Detuve la música y vacié la cola.")

    @app_commands.command(name="leave", description="Desconecta el bot del canal de voz")
    @app_commands.guild_only()
    async def leave(self, interaction: discord.Interaction) -> None:
        """Cierra la sesión y desconecta el bot del canal."""
        await controlled_session(interaction, self._registry).close()
        await interaction.response.send_message("👋 Me fui del canal de voz.")

    @app_commands.command(name="volume", description="Cambia el volumen del bot")
    @app_commands.describe(percent=f"Volumen de 0 a {MAX_VOLUME}")
    @app_commands.guild_only()
    async def volume(
        self, interaction: discord.Interaction, percent: app_commands.Range[int, 0, MAX_VOLUME]
    ) -> None:
        """Ajusta el volumen, que se mantiene entre canciones."""
        controlled_session(interaction, self._registry).set_volume(percent)
        await interaction.response.send_message(f"🔊 Volumen: {percent}%")

    @app_commands.command(name="nowplaying", description="Muestra la canción que está sonando")
    @app_commands.guild_only()
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        """Muestra la canción actual con su progreso."""
        session = existing_session(interaction, self._registry)
        await interaction.response.send_message(embed=now_playing_embed(session))
