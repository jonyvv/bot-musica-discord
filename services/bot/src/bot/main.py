import asyncio
import logging
import shutil

import discord
import httpx
from pydantic import SecretStr, ValidationError

from bot.application.inactivity import InactivityPolicy, Timeouts
from bot.application.registry import SessionRegistry
from bot.application.session import GuildSession, SessionSettings
from bot.application.timers import TimerRegistry
from bot.config import Settings
from bot.infrastructure.notifier import DiscordNotifier
from bot.infrastructure.resolver_client import HttpTrackResolver
from bot.infrastructure.secret_store import load_secret
from bot.infrastructure.voice import DiscordVoiceGateway
from bot.presentation.bot import MusicBot
from bot.presentation.limits import InteractionGate

logger = logging.getLogger(__name__)

FFMPEG_HINT = (
    "FFmpeg no está instalado o no está en el PATH. En Windows: winget install Gyan.FFmpeg"
)
TOKEN_HINT = "Discord rechazó el token. Generá uno nuevo en el portal (Bot > Reset Token)."
MISSING_TOKEN_HINT = (
    "Falta el token de Discord. Guardalo con: .\\scripts\\dev.ps1 token "
    "(o definí DISCORD_TOKEN como variable de entorno o secreto de Docker)."
)
GUILD_ACCESS_HINT = (
    "Discord dice que el bot no tiene acceso al servidor de DISCORD_GUILD_ID. Invitalo con el "
    "link de OAuth2 (permisos bot y applications.commands) y verificá que el ID sea el "
    "del servidor."
)
_STORED_SECRETS = ("discord_token", "resolver_api_key")


def load_settings(require_token: bool = True) -> Settings:
    """Lee la configuración; los secretos que falten se buscan en el almacén cifrado del sistema."""
    try:
        settings = Settings()
    except ValidationError as exc:
        fields = ", ".join(str(error["loc"][0]).upper() for error in exc.errors())
        message = f"Configuración inválida o incompleta ({fields}). Revisá el archivo .env."
        raise SystemExit(message) from exc
    settings = _fill_from_secret_store(settings)
    if require_token and not settings.discord_token.get_secret_value():
        raise SystemExit(MISSING_TOKEN_HINT)
    return settings


def _fill_from_secret_store(settings: Settings) -> Settings:
    """Completa con el almacén cifrado los secretos que no llegaron por entorno ni archivo."""
    missing = {
        name: SecretStr(stored)
        for name in _STORED_SECRETS
        if not getattr(settings, name).get_secret_value() and (stored := load_secret(name.upper()))
    }
    return settings.model_copy(update=missing)


def resolver_headers(settings: Settings) -> dict[str, str]:
    """Arma el header con la clave que autentica al bot frente al resolver, si hay una."""
    key = settings.resolver_api_key.get_secret_value()
    return {"Authorization": f"Bearer {key}"} if key else {}


def ensure_ffmpeg() -> None:
    """Falla al arrancar si FFmpeg no está disponible, en vez de fallar recién al reproducir."""
    if shutil.which("ffmpeg") is None:
        raise SystemExit(FFMPEG_HINT)


def build_bot(settings: Settings, http: httpx.AsyncClient) -> MusicBot:
    """Compone el bot: conecta los puertos de cada sesión con sus adaptadores concretos."""
    resolver = HttpTrackResolver(http)
    session_settings = SessionSettings(
        settings.default_volume,
        settings.max_queue_size,
        settings.max_tracks_per_user,
        settings.max_inflight_requests,
    )
    timeouts = Timeouts(settings.idle_timeout, settings.pause_timeout, settings.empty_timeout)

    def create_session(guild_id: int, on_closed) -> GuildSession:
        """Crea la sesión de un servidor con su voz, avisos y política de inactividad."""
        return GuildSession(
            guild_id=guild_id,
            resolver=resolver,
            voice=DiscordVoiceGateway(bot, guild_id),
            notifier=DiscordNotifier(bot),
            settings=session_settings,
            activity_factory=lambda close: InactivityPolicy(TimerRegistry(), timeouts, close),
            on_closed=on_closed,
        )

    gate = InteractionGate(
        settings.allowed_guilds,
        per_user=(settings.user_commands_per_10s, 10.0),
        per_guild=(settings.guild_commands_per_10s, 10.0),
    )
    bot = MusicBot(SessionRegistry(create_session), settings.discord_guild_id, gate)
    return bot


async def run() -> None:
    """Arranca el bot y mantiene abierto el cliente HTTP del resolver mientras viva."""
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    if not settings.resolver_api_key.get_secret_value():
        logger.warning("RESOLVER_API_KEY no está definida: el resolver recibirá pedidos sin clave")
    if not settings.allowed_guilds:
        logger.warning(
            "Sin DISCORD_GUILD_ID ni ALLOWED_GUILD_IDS: el bot opera en cualquier servidor"
        )
    ensure_ffmpeg()
    http_timeout = httpx.Timeout(120, connect=5)
    async with httpx.AsyncClient(
        base_url=settings.resolver_url,
        timeout=http_timeout,
        headers=resolver_headers(settings),
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    ) as http:
        bot = build_bot(settings, http)
        async with bot:
            try:
                await bot.start(settings.discord_token.get_secret_value())
            except discord.LoginFailure as exc:
                raise SystemExit(TOKEN_HINT) from exc
            except discord.Forbidden as exc:
                raise SystemExit(GUILD_ACCESS_HINT) from exc


def main() -> None:
    """Punto de entrada del proceso."""
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Bot detenido")


if __name__ == "__main__":
    main()
