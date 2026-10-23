import logging

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self, bot: commands.Bot):
        """Publica avisos del bot en un canal de texto, sin mencionar a nadie."""
        self._bot = bot
        self._channel_id: int | None = None

    def bind(self, channel_id: int) -> None:
        """Define el canal de texto donde se publican los avisos."""
        self._channel_id = channel_id

    async def send(self, text: str) -> None:
        """Publica un aviso; si el canal no existe o no se puede escribir, lo registra y sigue."""
        channel = self._bot.get_channel(self._channel_id) if self._channel_id else None
        if not isinstance(channel, discord.abc.Messageable):
            return
        try:
            await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            logger.warning("No se pudo enviar el aviso al canal %s: %s", self._channel_id, exc)
