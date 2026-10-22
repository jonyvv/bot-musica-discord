import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_TOO_LARGE = {"code": "payload_too_large", "message": "El pedido es demasiado grande."}


class BodyTooLargeError(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int):
        """Corta con 413 los pedidos cuyo cuerpo supera el máximo, declarado o transmitido."""
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Aplica el límite a los pedidos HTTP y deja pasar el resto de los tipos de conexión."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length", b"0")
        if declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(send)
            return
        received = 0
        exceeded = False

        async def limited_receive() -> Message:
            """Cuenta los bytes que van llegando y corta al pasarse del máximo."""
            nonlocal received, exceeded
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                exceeded = True
                raise BodyTooLargeError
            return message

        async def guarded_send(message: Message) -> None:
            """Reemplaza por un 413 cualquier respuesta que el framework arme tras un exceso."""
            if not exceeded:
                await send(message)
            elif message["type"] == "http.response.start":
                await self._reject(send)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except BodyTooLargeError:
            if exceeded:
                await self._reject(send)

    @staticmethod
    async def _reject(send: Send) -> None:
        """Responde 413 con el cuerpo de error estándar del servicio."""
        body = json.dumps(_TOO_LARGE).encode()
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ]
        await send({"type": "http.response.start", "status": 413, "headers": headers})
        await send({"type": "http.response.body", "body": body})
