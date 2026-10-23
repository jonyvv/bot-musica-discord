import asyncio
from collections import Counter

from uvicorn.protocols.http.h11_impl import H11Protocol

DEFAULT_HEADER_TIMEOUT = 10.0
DEFAULT_MAX_CONNECTIONS_PER_CLIENT = 32


class GuardedH11Protocol(H11Protocol):
    header_timeout = DEFAULT_HEADER_TIMEOUT
    max_per_client = DEFAULT_MAX_CONNECTIONS_PER_CLIENT
    open_by_client: Counter[str]

    def connection_made(self, transport: asyncio.Transport) -> None:  # type: ignore[override]
        """Cuenta la conexión del cliente, la corta si se pasó de su cupo y arranca el plazo."""
        super().connection_made(transport)
        self._header_deadline: asyncio.TimerHandle | None = None
        self._client_ip = self.client[0] if self.client else "desconocido"
        self.open_by_client[self._client_ip] += 1
        if self.max_per_client and self.open_by_client[self._client_ip] > self.max_per_client:
            transport.close()
            return
        self._arm_deadline()

    def data_received(self, data: bytes) -> None:
        """Mientras el pedido siga incompleto el plazo corre; al completarse se cancela."""
        super().data_received(data)
        if self._request_in_progress():
            self._disarm_deadline()
        else:
            self._arm_deadline()

    def connection_lost(self, exc: Exception | None) -> None:
        """Libera el cupo del cliente y cancela el plazo al cerrarse la conexión."""
        self._disarm_deadline()
        self.open_by_client[self._client_ip] -= 1
        if self.open_by_client[self._client_ip] <= 0:
            del self.open_by_client[self._client_ip]
        super().connection_lost(exc)

    def _request_in_progress(self) -> bool:
        """Indica si ya llegó un pedido completo que se está atendiendo."""
        return self.cycle is not None and not self.cycle.response_complete

    def _arm_deadline(self) -> None:
        """Programa el cierre de la conexión si no hay plazo corriendo; no se reinicia por byte."""
        if self._header_deadline is None and not self.transport.is_closing():
            self._header_deadline = self.loop.call_later(self.header_timeout, self._expire)

    def _disarm_deadline(self) -> None:
        """Cancela el plazo vigente, si lo hay."""
        if self._header_deadline is not None:
            self._header_deadline.cancel()
            self._header_deadline = None

    def _expire(self) -> None:
        """Cierra la conexión que no completó su pedido a tiempo."""
        self._header_deadline = None
        if not self.transport.is_closing():
            self.transport.close()


def guarded_protocol(
    header_timeout: float, max_per_client: int = DEFAULT_MAX_CONNECTIONS_PER_CLIENT
) -> type[GuardedH11Protocol]:
    """Crea el protocolo con su plazo de headers y su tope de conexiones por cliente."""
    attributes = {
        "header_timeout": header_timeout,
        "max_per_client": max_per_client,
        "open_by_client": Counter(),
    }
    return type("GuardedH11Protocol", (GuardedH11Protocol,), attributes)
