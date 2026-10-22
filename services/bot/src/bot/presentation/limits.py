import time
from collections.abc import Callable

import discord
from discord import app_commands

NOT_ALLOWED = "guild_not_allowed"


class InteractionGate:
    def __init__(
        self,
        allowed_guilds: frozenset[int] = frozenset(),
        per_user: tuple[int, float] = (8, 10.0),
        per_guild: tuple[int, float] = (30, 10.0),
        max_tracked: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ):
        """Filtra los comandos: solo servidores permitidos y con un tope por usuario y servidor."""
        self._allowed = allowed_guilds
        self._per_user = per_user
        self._per_guild = per_guild
        self._max_tracked = max_tracked
        self._clock = clock
        self._users: dict[int, app_commands.Cooldown] = {}
        self._guilds: dict[int, app_commands.Cooldown] = {}

    def allows(self, guild_id: int | None) -> bool:
        """Indica si el bot puede operar en ese servidor; sin lista configurada, en cualquiera."""
        return not self._allowed or guild_id in self._allowed

    async def check(self, interaction: discord.Interaction) -> bool:
        """Rechaza el comando si el servidor no está permitido o se excede el tope de uso."""
        if not self.allows(interaction.guild_id):
            raise app_commands.CheckFailure(NOT_ALLOWED)
        self._hit(self._users, interaction.user.id, self._per_user)
        if interaction.guild_id is not None:
            self._hit(self._guilds, interaction.guild_id, self._per_guild)
        return True

    def _hit(
        self, buckets: dict[int, app_commands.Cooldown], key: int, limit: tuple[int, float]
    ) -> None:
        """Registra un uso y falla con el tiempo de espera si se superó el tope de esa clave."""
        now = self._clock()
        cooldown = buckets.get(key)
        if cooldown is None:
            self._prune(buckets, now)
            cooldown = buckets[key] = app_commands.Cooldown(*limit)
        retry_after = cooldown.update_rate_limit(now)
        if retry_after:
            raise app_commands.CommandOnCooldown(cooldown, retry_after)

    def _prune(self, buckets: dict[int, app_commands.Cooldown], now: float) -> None:
        """Acota la memoria: descarta los contadores vencidos y, si hace falta, los más antiguos."""
        if len(buckets) < self._max_tracked:
            return
        for key in [k for k, cd in buckets.items() if cd.get_retry_after(now) == 0]:
            del buckets[key]
        for key in list(buckets)[: max(len(buckets) - self._max_tracked + 1, 0)]:
            del buckets[key]
