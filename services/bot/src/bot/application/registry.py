from collections.abc import Callable

from bot.application.session import GuildSession

SessionFactory = Callable[[int, Callable[[int], None]], GuildSession]


class SessionRegistry:
    def __init__(self, factory: SessionFactory):
        """Mantiene una sesión de reproducción por servidor, creándola bajo demanda."""
        self._factory = factory
        self._sessions: dict[int, GuildSession] = {}

    def get(self, guild_id: int) -> GuildSession | None:
        """Devuelve la sesión del servidor si existe."""
        return self._sessions.get(guild_id)

    def get_or_create(self, guild_id: int) -> GuildSession:
        """Devuelve la sesión del servidor, creándola si todavía no existe."""
        session = self._sessions.get(guild_id)
        if session is None:
            session = self._factory(guild_id, self.discard)
            self._sessions[guild_id] = session
        return session

    def discard(self, guild_id: int) -> None:
        """Olvida la sesión de un servidor cuando se cierra."""
        self._sessions.pop(guild_id, None)
