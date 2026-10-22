import asyncio
import logging
import math
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse

from resolver.application.service import ResolverService
from resolver.domain.errors import BotDetectedError, RateLimitedError, ResolverError
from resolver.presentation.auth import verify_api_key
from resolver.presentation.body_limit import BodySizeLimitMiddleware
from resolver.presentation.schemas import (
    ErrorSchema,
    ResolutionSchema,
    ResolveRequest,
    StreamSchema,
    TrackSchema,
)
from resolver.presentation.security import SecurityPolicy, SlidingWindowLimiter, throttle_requests

logger = logging.getLogger(__name__)

_STATUS_BY_CODE = {
    "rate_limited": 429,
    "unauthorized": 401,
    "unsupported_input": 422,
    "not_found": 404,
    "unavailable": 404,
    "spotify_unavailable": 404,
    "bot_detected": 503,
    "upstream_error": 502,
}
_ERRORS = {code: {"model": ErrorSchema} for code in set(_STATUS_BY_CODE.values())}

router = APIRouter(
    prefix="/v1",
    responses=_ERRORS,
    dependencies=[Depends(throttle_requests), Depends(verify_api_key)],
)


def get_service(request: Request) -> ResolverService:
    """Entrega el servicio de resolución guardado en el estado de la aplicación."""
    return request.app.state.service


@router.post("/resolve", response_model=ResolutionSchema)
async def resolve(
    body: ResolveRequest, service: ResolverService = Depends(get_service)
) -> ResolutionSchema:
    """Resuelve un link o texto de búsqueda en una o más canciones."""
    return ResolutionSchema.from_domain(await service.resolve(body.query))


@router.post("/stream", response_model=StreamSchema)
async def stream(
    body: TrackSchema, service: ResolverService = Depends(get_service)
) -> StreamSchema:
    """Obtiene la URL de audio reproducible de una canción ya resuelta."""
    return StreamSchema.from_domain(await service.stream(body.to_domain()))


def handle_resolver_error(_: Request, exc: ResolverError) -> JSONResponse:
    """Traduce un error de dominio a una respuesta JSON con código estable."""
    headers = {}
    if isinstance(exc, RateLimitedError):
        logger.debug("rate_limited message=%s", exc.message)
        headers["Retry-After"] = str(math.ceil(exc.retry_after))
    elif isinstance(exc, BotDetectedError):
        logger.error("DETECCION DE BOT: YouTube pidio verificacion. %s", exc.message)
    else:
        logger.warning("resolver_error code=%s message=%s", exc.code, exc.message)
    status = _STATUS_BY_CODE.get(exc.code, 502)
    content = {"code": exc.code, "message": exc.message}
    return JSONResponse(status_code=status, content=content, headers=headers)


def create_app(
    service: ResolverService,
    on_shutdown: Callable[[], Awaitable[None]] | None = None,
    background: Callable[[], Awaitable[None]] | None = None,
    security: SecurityPolicy | None = None,
) -> FastAPI:
    """Construye la aplicación HTTP con sus rutas, su manejo de errores y su ciclo de vida."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Corre la tarea de fondo mientras el servicio vive y cierra los recursos al apagarlo."""
        task = asyncio.create_task(background()) if background else None
        yield
        if task:
            task.cancel()
        if on_shutdown:
            await on_shutdown()

    app = FastAPI(
        title="Resolver", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None
    )
    policy = security or SecurityPolicy()
    app.state.service = service
    app.state.api_key_sha256 = policy.api_key_sha256
    app.state.request_limiter = (
        SlidingWindowLimiter(policy.requests_per_minute, 60) if policy.requests_per_minute else None
    )
    app.state.auth_failures = SlidingWindowLimiter(
        policy.auth_failure_limit, policy.auth_failure_window_seconds
    )
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=policy.max_body_bytes)
    app.include_router(router)
    app.add_exception_handler(ResolverError, handle_resolver_error)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Informa que el servicio está vivo."""
        return {"status": "ok"}

    return app
