import discord
from discord.ext import commands

from bot.application.registry import SessionRegistry


class VoiceEventsCog(commands.Cog):
    def __init__(self, registry: SessionRegistry):
        """Reacciona a los cambios de voz: limpia sesiones y detecta canales vacíos."""
        self._registry = registry

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        """Cierra la sesión si expulsan al bot y avisa cuando el canal se queda sin personas."""
        guild = member.guild
        session = self._registry.get(guild.id)
        if session is None:
            return
        if member.id == guild.me.id and after.channel is None:
            await session.close()
            return
        client = guild.voice_client
        if client is None or client.channel is None:
            return
        if any(not other.bot for other in client.channel.members):
            session.channel_occupied()
        else:
            session.channel_emptied()
