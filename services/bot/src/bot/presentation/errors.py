import logging

import discord
from discord import app_commands

from bot.domain.errors import BotError

logger = logging.getLogger(__name__)

_UNEXPECTED = "Ocurrió un error inesperado. Probá de nuevo en un momento."


def describe(error: app_commands.AppCommandError) -> str:
    """Convierte cualquier error de un comando en un mensaje seguro para mostrar al usuario."""
    original = getattr(error, "original", error)
    if isinstance(original, BotError):
        return original.user_message
    if isinstance(error, app_commands.CommandOnCooldown):
        return f"Esperá {error.retry_after:.0f} s antes de volver a usar este comando."
    if isinstance(error, app_commands.NoPrivateMessage):
        return "Este comando solo funciona dentro de un servidor."
    if isinstance(error, app_commands.CheckFailure):
        return "Este bot no está habilitado en este servidor."
    logger.error("Error inesperado en un comando", exc_info=original)
    return _UNEXPECTED


async def handle_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    """Responde al usuario con el error de su comando sin exponer detalles internos."""
    message = describe(error)
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)
