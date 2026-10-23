import asyncio
import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_TOO_LARGE = (413, {"code": "payload_too_large", "message": "El pedido es demasiado grande."})
_TOO_SLOW = (408, {"code": "request_timeout", "message": "El pedido tardó demasiado en llegar."})


class BodyRejectedError(Exception):
    def __init__(self, rejection: tuple[int, dict[str, str]]):
        """Señala que el cuerpo del pedido se rechaza, con el estado y el mensaje a devolver."""
        super().__init__(rejection[0])
        self.rejection = rejection


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int, body_timeout: float = 10.0):
        """Corta los pedidos con cuerpo demasiado grande (413) o que llega demasiado lento (408)."""
        self.app = app
        self.max_bytes = max_bytes
        self.body_timeout = body_timeout

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Aplica los límites a los pedidos HTTP y deja pasar el resto de los tipos de conexión."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length", b"0")
        if declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(send, _TOO_LARGE)
            return
        received = 0
        answered = False
        rejection: tuple[int, dict[str, str]] | None = None
        deadline = asyncio.get_running_loop().time() + self.body_timeout

        async def limited_receive() -> Message:
            """Cuenta bytes y tiempo del cuerpo, y corta al pasarse del máximo o del plazo."""
            nonlocal received, rejection
            remaining = deadline - asyncio.get_running_loop().time()
            try:
                message = await asyncio.wait_for(receive(), max(remaining, 0.001))
            except TimeoutError:
                rejection = _TOO_SLOW
                raise BodyRejectedError(_TOO_SLOW) from None
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                rejection = _TOO_LARGE
                raise BodyRejectedError(_TOO_LARGE)
            return message

        async def guarded_send(message: Message) -> None:
            """Reemplaza por el rechazo cualquier respuesta que el framework arme tras el corte."""
            nonlocal answered
            if message["type"] == "http.response.start":
                answered = True
            if rejection is None:
                await send(message)
            elif message["type"] == "http.response.start":
                await self._reject(send, rejection)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except BodyRejectedError as exc:
            if not answered:
                await self._reject(send, exc.rejection)

    @staticmethod
    async def _reject(send: Send, rejection: tuple[int, dict[str, str]]) -> None:
        """Responde con el estado y el cuerpo de error estándar del servicio."""
        status, content = rejection
        body = json.dumps(content).encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
