import asyncio
import logging
import shutil

import httpx
from pydantic import ValidationError

from bot.application.inactivity import InactivityPolicy, Timeouts
from bot.application.registry import SessionRegistry
from bot.application.session import GuildSession, SessionSettings
from bot.application.timers import TimerRegistry
from bot.config import Settings
from bot.infrastructure.notifier import DiscordNotifier
from bot.infrastructure.resolver_client import HttpTrackResolver
from bot.infrastructure.voice import DiscordVoiceGateway
from bot.presentation.bot import MusicBot

FFMPEG_HINT = (
    "FFmpeg no está instalado o no está en el PATH. En Windows: winget install Gyan.FFmpeg"
)


def load_settings() -> Settings:
    """Lee la configuración del entorno y falla con un mensaje claro si falta algo."""
    try:
        return Settings()
    except ValidationError as exc:
        fields = ", ".join(str(error["loc"][0]).upper() for error in exc.errors())
        message = f"Configuración inválida o incompleta ({fields}). Revisá el archivo .env."
        raise SystemExit(message) from exc


def ensure_ffmpeg() -> None:
    """Falla al arrancar si FFmpeg no está disponible, en vez de fallar recién al reproducir."""
    if shutil.which("ffmpeg") is None:
        raise SystemExit(FFMPEG_HINT)


def build_bot(settings: Settings, http: httpx.AsyncClient) -> MusicBot:
    """Compone el bot: conecta los puertos de cada sesión con sus adaptadores concretos."""
    resolver = HttpTrackResolver(http)
    session_settings = SessionSettings(settings.default_volume, settings.max_queue_size)
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

    bot = MusicBot(SessionRegistry(create_session), settings.discord_guild_id)
    return bot


async def run() -> None:
    """Arranca el bot y mantiene abierto el cliente HTTP del resolver mientras viva."""
    settings = load_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    ensure_ffmpeg()
    timeout = httpx.Timeout(120, connect=5)
    async with httpx.AsyncClient(base_url=settings.resolver_url, timeout=timeout) as http:
        bot = build_bot(settings, http)
        async with bot:
            await bot.start(settings.discord_token.get_secret_value())


def main() -> None:
    """Punto de entrada del proceso."""
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Bot detenido")


if __name__ == "__main__":
    main()
