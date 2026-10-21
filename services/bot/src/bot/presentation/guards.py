import discord

from bot.application.registry import SessionRegistry
from bot.application.session import GuildSession
from bot.domain.errors import BotError

VoiceChannel = discord.VoiceChannel | discord.StageChannel


def guild_of(interaction: discord.Interaction) -> discord.Guild:
    """Devuelve el servidor del comando o falla si se usó fuera de uno."""
    if interaction.guild is None:
        raise BotError("Este comando solo funciona dentro de un servidor.")
    return interaction.guild


def voice_channel_of(interaction: discord.Interaction) -> VoiceChannel:
    """Devuelve el canal de voz de quien usa el comando o falla si no está en ninguno."""
    voice = getattr(interaction.user, "voice", None)
    if voice is None or voice.channel is None:
        raise BotError("Tenés que estar en un canal de voz para usar este comando.")
    return voice.channel


def require_permissions(channel: VoiceChannel, me: discord.Member) -> None:
    """Verifica que el bot pueda conectarse, hablar y entrar al canal."""
    permissions = channel.permissions_for(me)
    if not (permissions.connect and permissions.speak):
        raise BotError(f"No tengo permisos para conectarme y hablar en {channel.mention}.")
    full = bool(channel.user_limit) and len(channel.members) >= channel.user_limit
    if full and not permissions.move_members:
        raise BotError(f"El canal {channel.mention} está lleno.")


def require_same_channel(session: GuildSession, channel: VoiceChannel) -> None:
    """Exige que quien usa el comando esté en el mismo canal donde suena el bot."""
    if session.channel_id is not None and session.channel_id != channel.id:
        raise BotError("Estoy reproduciendo en otro canal de voz.")


def existing_session(interaction: discord.Interaction, registry: SessionRegistry) -> GuildSession:
    """Devuelve la sesión activa del servidor o falla si el bot no está reproduciendo."""
    session = registry.get(guild_of(interaction).id)
    if session is None or session.channel_id is None:
        raise BotError("No estoy reproduciendo nada.")
    return session


def controlled_session(interaction: discord.Interaction, registry: SessionRegistry) -> GuildSession:
    """Devuelve la sesión activa exigiendo que quien manda el comando esté en su canal."""
    session = existing_session(interaction, registry)
    require_same_channel(session, voice_channel_of(interaction))
    return session


def play_target(
    interaction: discord.Interaction, registry: SessionRegistry
) -> tuple[GuildSession, VoiceChannel]:
    """Valida un pedido de reproducción y devuelve la sesión y el canal donde sonará."""
    guild = guild_of(interaction)
    channel = voice_channel_of(interaction)
    require_permissions(channel, guild.me)
    session = registry.get_or_create(guild.id)
    require_same_channel(session, channel)
    return session, channel
