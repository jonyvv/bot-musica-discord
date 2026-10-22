import json

from starlette.types import ASGIApp, Receive, Scope, Send

_BUSY = {"code": "rate_limited", "message": "Hay demasiados pedidos en curso desde tu conexión."}
_EXEMPT_PATHS = {"/health"}


class InflightLimitMiddleware:
    def __init__(self, app: ASGIApp, per_client: int):
        """Limita los pedidos simultáneos de cada cliente para que ninguno acapare el servicio."""
        self.app = app
        self.per_client = per_client
        self._active: dict[str, int] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Rechaza de inmediato, sin procesar nada, al cliente que ya llegó a su tope."""
        if scope["type"] != "http" or scope["path"] in _EXEMPT_PATHS or self.per_client <= 0:
            await self.app(scope, receive, send)
            return
        client = scope["client"][0] if scope.get("client") else "desconocido"
        if self._active.get(client, 0) >= self.per_client:
            await self._reject(send)
            return
        self._active[client] = self._active.get(client, 0) + 1
        try:
            await self.app(scope, receive, send)
        finally:
            self._release(client)

    def _release(self, client: str) -> None:
        """Libera un lugar del cliente y olvida su contador cuando llega a cero."""
        remaining = self._active.get(client, 1) - 1
        if remaining <= 0:
            self._active.pop(client, None)
        else:
            self._active[client] = remaining

    @staticmethod
    async def _reject(send: Send) -> None:
        """Responde 429 con el cuerpo de error estándar y pide esperar un segundo."""
        body = json.dumps(_BUSY).encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"retry-after", b"1"),
        ]
        await send({"type": "http.response.start", "status": 429, "headers": headers})
        await send({"type": "http.response.body", "body": body})
