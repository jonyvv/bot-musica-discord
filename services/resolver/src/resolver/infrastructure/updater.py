import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable, Sequence

logger = logging.getLogger(__name__)

Runner = Callable[[Sequence[str]], Awaitable[tuple[int, str]]]

_UPGRADE = [
    sys.executable,
    "-m",
    "pip",
    "install",
    "--user",
    "--quiet",
    "--upgrade",
    "yt-dlp[default]",
]
_VERSION = [sys.executable, "-c", "import importlib.metadata as m; print(m.version('yt-dlp'))"]
_LOG_TAIL = 300


async def run_command(args: Sequence[str]) -> tuple[int, str]:
    """Ejecuta un comando y devuelve su código de salida junto con su salida combinada."""
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    output, _ = await process.communicate()
    return process.returncode or 0, output.decode(errors="replace").strip()


class YtDlpUpdater:
    def __init__(
        self,
        interval_seconds: int,
        on_updated: Callable[[], None],
        runner: Runner = run_command,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        """Busca versiones nuevas de yt-dlp y avisa para que el servicio se reinicie con ella."""
        self._interval = interval_seconds
        self._on_updated = on_updated
        self._runner = runner
        self._sleep = sleep

    async def run_forever(self) -> None:
        """Revisa al arrancar y luego cada intervalo; termina cuando encuentra una versión nueva."""
        while not await self.check_once():
            await self._sleep(self._interval)

    async def check_once(self) -> bool:
        """Intenta actualizar yt-dlp y devuelve True si la versión instalada cambió."""
        before = await self._installed_version()
        code, output = await self._runner(_UPGRADE)
        if code != 0:
            logger.warning("No se pudo actualizar yt-dlp: %s", output[-_LOG_TAIL:])
            return False
        after = await self._installed_version()
        if before is None or after is None or before == after:
            return False
        logger.info("yt-dlp actualizado de %s a %s; reiniciando el servicio", before, after)
        self._on_updated()
        return True

    async def _installed_version(self) -> str | None:
        """Lee la versión de yt-dlp instalada en disco, sin depender de lo ya importado."""
        code, output = await self._runner(_VERSION)
        return output if code == 0 and output else None
