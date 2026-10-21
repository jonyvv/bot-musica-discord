import asyncio
from collections.abc import Awaitable, Callable


class TimerRegistry:
    def __init__(self, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        """Conjunto de temporizadores con nombre, de a uno por nombre y cancelables."""
        self._sleep = sleep
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def active(self) -> frozenset[str]:
        """Nombres de los temporizadores que siguen corriendo."""
        return frozenset(self._tasks)

    def start(self, name: str, delay: float, callback: Callable[[], Awaitable[None]]) -> None:
        """Programa `callback` tras `delay` segundos, reemplazando el temporizador homónimo."""
        self.cancel(name)
        self._tasks[name] = asyncio.create_task(self._run(name, delay, callback))

    def cancel(self, name: str) -> None:
        """Cancela el temporizador si existe."""
        task = self._tasks.pop(name, None)
        if task is not None:
            task.cancel()

    def cancel_all(self) -> None:
        """Cancela todos los temporizadores."""
        for name in list(self._tasks):
            self.cancel(name)

    async def _run(self, name: str, delay: float, callback: Callable[[], Awaitable[None]]) -> None:
        """Espera el plazo y ejecuta el aviso, quitándose antes para no cancelarse a sí mismo."""
        await self._sleep(delay)
        if self._tasks.get(name) is asyncio.current_task():
            del self._tasks[name]
        await callback()
